"""TD-09: read-only evidence for the Windows host companion; no secrets/rows.

Executed inside the already selected running backend container. Uses its actual
runtime engine. Does not import main, migrate, start services or mutate data.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from sqlalchemy import inspect, text
from app.services.maintenance_runtime_preflight import read_runtime_schema_evidence

EPHEMERAL = frozenset({'maintenance_control','maintenance_operations','maintenance_audit','server_sessions','auth_audit_log','alembic_version'})


def collect(conn):
    conn.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    conn.exec_driver_sql("SET LOCAL TIME ZONE 'UTC'")
    control = conn.execute(text('SELECT state,cycle_id FROM maintenance_control WHERE id=1')).mappings().one()
    runtime = read_runtime_schema_evidence(conn, alembic_ini=Path(__file__).resolve().parents[2]/'alembic.ini')
    runtime['release_version'] = (Path(__file__).resolve().parents[2]/'VERSION.txt').read_text().strip()
    runtime['database_oid'] = str(conn.execute(text('SELECT oid FROM pg_database WHERE datname=current_database()')).scalar_one())
    active = int(conn.execute(text('SELECT count(*) FROM maintenance_operations WHERE finished_at IS NULL')).scalar_one())
    if control['state'] not in {'draining','locked','verifying','blocked'} or active:
        return {**dict(control),'active_operations':active,'database_runtime':runtime}
    tables = sorted(set(inspect(conn).get_table_names())-EPHEMERAL)
    if not tables:
        raise RuntimeError('No domain tables to prove')
    q = conn.dialect.identifier_preparer.quote_identifier
    statements=[]
    fingerprints=[]
    for table in tables:
        sql = f"SELECT json_build_object('table', :table, 'rows', count(*), 'digest', md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY md5(row_to_json(t)::text)),''))) FROM {q(runtime['schema_name'])}.{q(table)} AS t"
        fingerprints.append(conn.execute(text(sql),{'table':table}).scalar_one())
        # Table identifiers come only from the inspected database, not a caller.
        statements.append(sql.replace(':table', "'"+table.replace("'","''")+"'"))
    sequences = conn.execute(text("""
        SELECT seq.relname FROM pg_class seq
        JOIN pg_namespace n ON n.oid=seq.relnamespace
        JOIN pg_depend d ON d.objid=seq.oid AND d.classid='pg_class'::regclass AND d.deptype IN ('a','i')
        JOIN pg_class owner_table ON owner_table.oid=d.refobjid
        WHERE seq.relkind='S' AND n.nspname=current_schema()
          AND owner_table.relname = ANY(CAST(:tables AS text[]))
        ORDER BY seq.relname
    """), {'tables':tables}).scalars().all()
    for sequence in sequences:
        label = 'sequence:'+sequence
        sql = f"SELECT json_build_object('table', :table, 'rows', 1, 'digest', md5(row_to_json(t)::text)) FROM (SELECT last_value,is_called FROM {q(runtime['schema_name'])}.{q(sequence)}) t"
        fingerprints.append(conn.execute(text(sql),{'table':label}).scalar_one())
        statements.append(sql.replace(':table', "'"+label.replace("'","''")+"'"))
    canonical=json.dumps(fingerprints,sort_keys=True,separators=(',',':'))
    return {'state':control['state'],'cycle_id':control['cycle_id'],'active_operations':int(conn.execute(text('SELECT count(*) FROM maintenance_operations WHERE finished_at IS NULL')).scalar_one()),'database_runtime':runtime,
            'fingerprints':fingerprints,'domain_fingerprint':hashlib.sha256(canonical.encode()).hexdigest(),
            'fingerprint_sql':"SET TIME ZONE 'UTC';\n"+';\n'.join(statements)+';'}


def main():
    from app.db import engine
    with engine.begin() as conn:
        print(json.dumps(collect(conn),sort_keys=True,default=str))

if __name__=='__main__':
    main()
