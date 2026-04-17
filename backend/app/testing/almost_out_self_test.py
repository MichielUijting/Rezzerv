from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy import text

TEST_HOUSEHOLD_ID = '__almost_out_self_test__'
TEST_PREFIX = '[almost-out-self-test]'


@dataclass
class ScenarioDefinition:
    scenario_id: str
    name: str
    expected_status: str
    min_stock: float | None
    article_name: str
    inventory_rows: list[dict[str, Any]]
    event_rows: list[dict[str, Any]]
    expected_almost_out: bool | None
    expected_total_quantity: float | None
    notes: str = ''


def _main_api():
    from app import main as api
    return api


def _cleanup_household(conn, household_id: str) -> None:
    conn.execute(text('DELETE FROM inventory_events WHERE household_id = :household_id'), {'household_id': household_id})
    conn.execute(text('DELETE FROM inventory WHERE household_id = :household_id'), {'household_id': household_id})
    conn.execute(
        text(
            '''
            DELETE FROM household_article_settings
            WHERE household_article_id IN (
              SELECT id FROM household_articles WHERE household_id = :household_id
            )
            '''
        ),
        {'household_id': household_id},
    )
    conn.execute(
        text(
            '''
            DELETE FROM household_article_notes
            WHERE household_article_id IN (
              SELECT id FROM household_articles WHERE household_id = :household_id
            )
            '''
        ),
        {'household_id': household_id},
    )
    conn.execute(text('DELETE FROM household_articles WHERE household_id = :household_id'), {'household_id': household_id})
    conn.execute(
        text(
            '''
            DELETE FROM sublocations
            WHERE space_id IN (
              SELECT id FROM spaces WHERE household_id = :household_id
            )
            '''
        ),
        {'household_id': household_id},
    )
    conn.execute(text('DELETE FROM spaces WHERE household_id = :household_id'), {'household_id': household_id})
    conn.execute(
        text(
            'DELETE FROM household_settings WHERE household_id = :household_id AND setting_key IN (:a, :b, :c)'
        ),
        {
            'household_id': household_id,
            'a': 'almost_out_prediction_enabled',
            'b': 'almost_out_prediction_days',
            'c': 'almost_out_policy_mode',
        },
    )


def _ensure_space(conn, household_id: str, name: str) -> str:
    existing = conn.execute(
        text('SELECT id FROM spaces WHERE household_id = :household_id AND lower(trim(naam)) = lower(trim(:name)) LIMIT 1'),
        {'household_id': household_id, 'name': name},
    ).mappings().first()
    if existing and existing.get('id'):
        return str(existing['id'])
    space_id = str(uuid4())
    conn.execute(
        text('INSERT INTO spaces (id, naam, household_id, active) VALUES (:id, :naam, :household_id, 1)'),
        {'id': space_id, 'naam': name, 'household_id': household_id},
    )
    return space_id


def _ensure_sublocation(conn, space_id: str, name: str) -> str:
    existing = conn.execute(
        text('SELECT id FROM sublocations WHERE space_id = :space_id AND lower(trim(naam)) = lower(trim(:name)) LIMIT 1'),
        {'space_id': space_id, 'name': name},
    ).mappings().first()
    if existing and existing.get('id'):
        return str(existing['id'])
    sublocation_id = str(uuid4())
    conn.execute(
        text('INSERT INTO sublocations (id, naam, space_id, active) VALUES (:id, :naam, :space_id, 1)'),
        {'id': sublocation_id, 'naam': name, 'space_id': space_id},
    )
    return sublocation_id


def _seed_scenario(conn, household_id: str, scenario: ScenarioDefinition) -> dict[str, Any]:
    api = _main_api()
    _cleanup_household(conn, household_id)

    article_id = str(uuid4())
    conn.execute(
        text(
            '''
            INSERT INTO household_articles (
              id, household_id, naam, consumable, min_stock, ideal_stock, status, updated_at
            ) VALUES (
              :id, :household_id, :naam, 1, :min_stock, :ideal_stock, 'active', CURRENT_TIMESTAMP
            )
            '''
        ),
        {
            'id': article_id,
            'household_id': household_id,
            'naam': scenario.article_name,
            'min_stock': scenario.min_stock,
            'ideal_stock': (scenario.min_stock + 1) if scenario.min_stock is not None else None,
        },
    )
    api.set_household_almost_out_settings(
        conn,
        household_id,
        prediction_enabled=False,
        prediction_days=14,
        policy_mode=api.ALMOST_OUT_POLICY_ADVISORY,
    )

    first_space_id = None
    for row in scenario.inventory_rows:
        space_name = row.get('space_name') or 'Keuken'
        sublocation_name = row.get('sublocation_name')
        space_id = _ensure_space(conn, household_id, space_name)
        first_space_id = first_space_id or space_id
        sublocation_id = _ensure_sublocation(conn, space_id, sublocation_name) if sublocation_name else None
        conn.execute(
            text(
                '''
                INSERT INTO inventory (id, naam, aantal, household_id, space_id, sublocation_id, status, updated_at)
                VALUES (:id, :naam, :aantal, :household_id, :space_id, :sublocation_id, 'active', CURRENT_TIMESTAMP)
                '''
            ),
            {
                'id': str(uuid4()),
                'naam': scenario.article_name,
                'aantal': int(row.get('quantity') or 0),
                'household_id': household_id,
                'space_id': space_id,
                'sublocation_id': sublocation_id,
            },
        )

    default_space_id = first_space_id or _ensure_space(conn, household_id, 'Keuken')
    for idx, row in enumerate(scenario.event_rows, start=1):
        location_id = default_space_id
        location_label = row.get('space_name') or 'Keuken'
        if row.get('space_name'):
            location_id = _ensure_space(conn, household_id, str(row.get('space_name')))
            location_label = str(row.get('space_name'))
        conn.execute(
            text(
                '''
                INSERT INTO inventory_events (
                  id, household_id, article_id, article_name, location_id, location_label,
                  event_type, quantity, old_quantity, new_quantity, source, note, created_at
                ) VALUES (
                  :id, :household_id, :article_id, :article_name, :location_id, :location_label,
                  :event_type, :quantity, :old_quantity, :new_quantity, :source, :note,
                  datetime('now', :offset)
                )
                '''
            ),
            {
                'id': str(uuid4()),
                'household_id': household_id,
                'article_id': article_id,
                'article_name': scenario.article_name,
                'location_id': location_id,
                'location_label': location_label,
                'event_type': row.get('event_type') or 'adjustment',
                'quantity': row.get('quantity') or 0,
                'old_quantity': row.get('old_quantity'),
                'new_quantity': row.get('new_quantity'),
                'source': row.get('source') or 'self_test',
                'note': f"{TEST_PREFIX} {scenario.scenario_id} #{idx}",
                'offset': f'+{idx} seconds',
            },
        )
    return {'household_article_id': article_id}


def _calculate_event_net_quantity(event_rows: Iterable[dict[str, Any]]) -> float:
    total = 0.0
    for row in event_rows:
        try:
            total += float(row.get('quantity') or 0)
        except (TypeError, ValueError):
            continue
    return total


def _run_single_scenario(conn, household_id: str, scenario: ScenarioDefinition) -> dict[str, Any]:
    seeded = _seed_scenario(conn, household_id, scenario)
    api = _main_api()
    article_row = api.get_household_article_row_by_id(conn, household_id, seeded['household_article_id'])
    evaluation = api.evaluate_household_article_almost_out(conn, household_id, article_row)
    total_quantity = float(evaluation.get('current_quantity') or 0)
    items = api.build_almost_out_items(conn, household_id)
    matched = None
    for item in items:
        if str(item.get('household_article_id') or '') == seeded['household_article_id']:
            matched = item
            break
    actual_almost_out = bool(evaluation.get('include_in_almost_out')) and matched is not None
    actual_data_state = str(evaluation.get('data_state') or 'ok')
    is_inconsistent = actual_data_state == api.ALMOST_OUT_DATA_STATE_INCONSISTENT
    actual_status = 'blocked' if scenario.expected_status == 'blocked' and is_inconsistent else ('passed' if actual_almost_out == scenario.expected_almost_out and (scenario.expected_total_quantity is None or abs(total_quantity - scenario.expected_total_quantity) <= 1e-9) else 'failed')

    error = None
    if actual_status == 'failed':
        error = (
            f"Verwacht almost_out={scenario.expected_almost_out}, quantity={scenario.expected_total_quantity}; "
            f"kreeg almost_out={actual_almost_out}, quantity={total_quantity}"
        )
    elif actual_status == 'blocked':
        error = str(evaluation.get('data_state_message') or 'Inconsistente toestand gedetecteerd.')

    event_net = _calculate_event_net_quantity(scenario.event_rows)
    return {
        'name': scenario.name,
        'scenario_id': scenario.scenario_id,
        'status': actual_status,
        'error': error,
        'details': {
            'article_name': scenario.article_name,
            'household_article_id': seeded['household_article_id'],
            'expected_almost_out': scenario.expected_almost_out,
            'actual_almost_out': actual_almost_out,
            'expected_total_quantity': scenario.expected_total_quantity,
            'actual_total_quantity': total_quantity,
            'expected_status': scenario.expected_status,
            'event_net_quantity': event_net,
            'returned_items': items,
            'notes': scenario.notes,
        },
    }


def scenario_definitions() -> list[ScenarioDefinition]:
    return [
        ScenarioDefinition('above_min', 'Boven minimum: artikel verschijnt niet', 'passed', 5, 'SELFTEST Above Min', [{'space_name': 'Keuken', 'quantity': 10}], [], False, 10),
        ScenarioDefinition('equal_min', 'Gelijk aan minimum: artikel verschijnt wel', 'passed', 5, 'SELFTEST Equal Min', [{'space_name': 'Keuken', 'quantity': 5}], [], True, 5),
        ScenarioDefinition('below_min', 'Onder minimum: artikel verschijnt wel', 'passed', 5, 'SELFTEST Below Min', [{'space_name': 'Keuken', 'quantity': 4}], [], True, 4),
        ScenarioDefinition('zero_stock', 'Nul voorraad: artikel verschijnt wel', 'passed', 5, 'SELFTEST Zero Stock', [{'space_name': 'Keuken', 'quantity': 0}], [], True, 0),
        ScenarioDefinition(
            'consume_event_crosses_threshold',
            'Consume-event zakt onder minimum',
            'passed',
            5,
            'SELFTEST Consume Threshold',
            [{'space_name': 'Keuken', 'quantity': 4}],
            [
                {'event_type': 'purchase', 'quantity': 10, 'old_quantity': 0, 'new_quantity': 10},
                {'event_type': 'consume', 'quantity': -6, 'old_quantity': 10, 'new_quantity': 4},
            ],
            True,
            4,
        ),
        ScenarioDefinition(
            'multiple_events_net_result',
            'Meerdere events: netto eindsaldo bepaalt almost-out',
            'passed',
            5,
            'SELFTEST Multiple Events',
            [{'space_name': 'Keuken', 'quantity': 5}],
            [
                {'event_type': 'purchase', 'quantity': 10, 'old_quantity': 0, 'new_quantity': 10},
                {'event_type': 'consume', 'quantity': -7, 'old_quantity': 10, 'new_quantity': 3},
                {'event_type': 'adjustment', 'quantity': 2, 'old_quantity': 3, 'new_quantity': 5},
            ],
            True,
            5,
        ),
        ScenarioDefinition(
            'multiple_locations_total_stock',
            'Meerdere locaties: totaalvoorraad bepaalt almost-out',
            'passed',
            5,
            'SELFTEST Multi Location',
            [
                {'space_name': 'Keuken', 'quantity': 3},
                {'space_name': 'Berging', 'quantity': 3},
            ],
            [
                {'event_type': 'purchase', 'quantity': 3, 'space_name': 'Keuken', 'old_quantity': 0, 'new_quantity': 3},
                {'event_type': 'purchase', 'quantity': 3, 'space_name': 'Berging', 'old_quantity': 0, 'new_quantity': 3},
            ],
            False,
            6,
        ),
        ScenarioDefinition('null_min_stock', 'Geen min_stock: artikel verschijnt niet', 'passed', None, 'SELFTEST Null Min', [{'space_name': 'Keuken', 'quantity': 5}], [], False, 5),
        ScenarioDefinition(
            'invalid_or_inconsistent_state',
            'Inconsistente toestand wordt geblokkeerd',
            'blocked',
            5,
            'SELFTEST Invalid State',
            [{'space_name': 'Keuken', 'quantity': 2}],
            [
                {'event_type': 'purchase', 'quantity': 10, 'old_quantity': 0, 'new_quantity': 10},
                {'event_type': 'consume', 'quantity': -1, 'old_quantity': 10, 'new_quantity': 9},
            ],
            None,
            2,
            notes='Deze self-test accepteert inconsistente inventory/event-data niet stilzwijgend.',
        ),
    ]


def run_almost_out_backend_self_test(engine) -> dict[str, Any]:
    household_id = TEST_HOUSEHOLD_ID
    results: list[dict[str, Any]] = []
    with engine.begin() as conn:
        _cleanup_household(conn, household_id)
        for scenario in scenario_definitions():
            results.append(_run_single_scenario(conn, household_id, scenario))
        _cleanup_household(conn, household_id)
    passed = sum(1 for item in results if item['status'] == 'passed')
    blocked = sum(1 for item in results if item['status'] == 'blocked')
    failed = sum(1 for item in results if item['status'] == 'failed')
    overall = 'failed' if failed else 'passed'
    return {
        'test_type': 'almost_out_self_test',
        'status': overall,
        'passed_count': passed,
        'blocked_count': blocked,
        'failed_count': failed,
        'household_id': household_id,
        'results': results,
    }
