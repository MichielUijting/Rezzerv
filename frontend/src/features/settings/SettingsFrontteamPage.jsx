import React from 'react'
import { API_BASE_URL } from '../../lib/apiClient.js'
import Button from '../../ui/Button.jsx'
import Card from '../../ui/Card.jsx'
import DataTable from '../../ui/DataTable.jsx'
import './settingsHousehold.css'

const FRONTTEAM_ROLE_KEY = 'platform.frontteam'

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || `Actie mislukt (${response.status})`)
  return payload
}

function isActiveMember(member) {
  return (
    <div data-testid="settings-frontteam-page">
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card>
            <div className="rz-frontteam-content">
              <h2>Frontteam beheren — {members.length} {members.length === 1 ? 'lid' : 'leden'}</h2>

              <form onSubmit={addMember} data-testid="frontteam-add-form" className="rz-frontteam-add-form">
                <div className="rz-input-field">
                  <label className="rz-label" htmlFor="frontteam-email">Lid toevoegen aan Frontteam</label>
                  <div className="rz-frontteam-add-row">
                    <input
                      id="frontteam-email"
                      className="rz-input"
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder="E-mailadres van bestaande Inhuis-gebruiker"
                      autoComplete="off"
                    />
                    <Button type="submit" disabled={busy}>{busy ? 'Bezig...' : 'Toevoegen'}</Button>
                  </div>
                </div>
                <p className="rz-frontteam-help">Het eigen huishouden en de huishoudrol blijven ongewijzigd.</p>
              </form>

              {error ? <div role="alert" className="rz-frontteam-error">{error}</div> : null}
              {result ? <div role="status" className="rz-frontteam-result">{result}</div> : null}

              <DataTable
                columns={columns}
                data={members}
                getRowKey={(member) => member.user_id}
                emptyMessage={loading ? 'Frontteamleden laden…' : 'Er zijn nog geen Frontteamleden.'}
                dataTestId="frontteam-members-table"
                pagination
                pageSize={10}
                stickyHeader
                stickyFilters
                renderRow={(member) => (
                  <tr
                    key={member.user_id}
                    data-testid={`frontteam-member-${member.user_id}`}
                    className={selectedIds.includes(member.user_id) ? 'rz-row-selected' : ''}
                  >
                    {columns.map((column) => (
                      <td key={column.key}>
                        {column.renderCell ? column.renderCell(member) : String(column.getValue ? column.getValue(member) : member[column.key] ?? '')}
                      </td>
                    ))}
                  </tr>
                )}
              />

              <div className="rz-frontteam-bulk-actions">
                <Button type="button" disabled={busy || !someSelected} onClick={() => setSelectedActive(true)}>Activeren</Button>
                <Button type="button" disabled={busy || !someSelected} onClick={() => setSelectedActive(false)}>Deactiveren</Button>
                <Button type="button" disabled={busy || !someSelected} onClick={removeSelected}>Verwijderen</Button>
                <Button type="button" disabled={busy || !someSelected} onClick={exportSelected}>Exporteren</Button>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
