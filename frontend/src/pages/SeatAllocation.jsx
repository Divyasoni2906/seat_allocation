import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getAvailableSeats, getEmployees, getEmployee, getOccupiedSeats, getSeats, getProjects, allocateSeat, releaseSeat, uploadSeatsCSV, updateSeatStatus } from '../api.js'

export default function SeatAllocation() {
  const queryClient = useQueryClient()
  const [floor, setFloor] = useState('')
  const [zone, setZone] = useState('')
  const [employeeQuery, setEmployeeQuery] = useState('')
  const [selectedEmployeeId, setSelectedEmployeeId] = useState('')
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [preferredFloor, setPreferredFloor] = useState('')
  const [preferredZone, setPreferredZone] = useState('')
  const [message, setMessage] = useState(null)
  const [csvResult, setCsvResult] = useState(null)
  const [csvUploading, setCsvUploading] = useState(false)

  const { data: availableSeats, isLoading: loadingSeats } = useQuery({
    queryKey: ['available-seats', floor, zone],
    queryFn: () => getAvailableSeats({ floor: floor || undefined, zone: zone || undefined, limit: 50 }),
  })

  const { data: employeeOptions } = useQuery({
    queryKey: ['employee-options', employeeQuery],
    queryFn: () => getEmployees({ search: employeeQuery || undefined, limit: 10 }),
    enabled: employeeQuery.length > 0,
  })

  const { data: projects } = useQuery({ queryKey: ['projects'], queryFn: getProjects })

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['available-seats'] })
    queryClient.invalidateQueries({ queryKey: ['occupied-seats'] })
    queryClient.invalidateQueries({ queryKey: ['employees'] })
    queryClient.invalidateQueries({ queryKey: ['employee-options'] })
    queryClient.invalidateQueries({ queryKey: ['employee-options-release'] })
    queryClient.invalidateQueries({ queryKey: ['employee-detail-allocate'] })
    queryClient.invalidateQueries({ queryKey: ['employee-detail-release'] })
    queryClient.invalidateQueries({ queryKey: ['project-employees'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] })
    queryClient.invalidateQueries({ queryKey: ['project-utilization'] })
    queryClient.invalidateQueries({ queryKey: ['floor-utilization'] })
  }

  const allocateMutation = useMutation({
    mutationFn: allocateSeat,
    onSuccess: (data) => {
      setMessage({
        type: 'success',
        text: `Allocated seat ${data.seat.seat_number} (Floor ${data.seat.floor}, Zone ${data.seat.zone})${
          data.alternate_zone ? ' — preferred zone was full, used an alternate zone.' : ''
        }`,
      })
      setEmployeeQuery('')
      setSelectedEmployeeId('')
      setSelectedProjectId('')
      setPreferredFloor('')
      setPreferredZone('')
      invalidateAll()
    },
    onError: (err) => {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Allocation failed' })
    },
  })

  const { data: selectedEmployeeDetail } = useQuery({
    queryKey: ['employee-detail-allocate', selectedEmployeeId],
    queryFn: () => getEmployee(selectedEmployeeId),
    enabled: !!selectedEmployeeId,
  })

  const releaseMutation = useMutation({
    mutationFn: releaseSeat,
    onSuccess: (data) => {
      setMessage({
        type: 'success',
        text: data.seat
          ? `Released seat ${data.seat.seat_number} (Floor ${data.seat.floor}, Zone ${data.seat.zone}). It's now available.`
          : 'Seat released successfully.',
      })
      setReleaseEmployeeId('')
      setReleaseEmployeeQuery('')
      invalidateAll()
    },
    onError: (err) => {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Release failed' })
    },
  })

  const [releaseEmployeeQuery, setReleaseEmployeeQuery] = useState('')
  const [releaseEmployeeId, setReleaseEmployeeId] = useState('')

  const { data: releaseEmployeeOptions } = useQuery({
    queryKey: ['employee-options-release', releaseEmployeeQuery],
    queryFn: () => getEmployees({ search: releaseEmployeeQuery || undefined, limit: 10 }),
    enabled: releaseEmployeeQuery.length > 0 && !releaseEmployeeId,
  })

  const { data: releaseEmployeeDetail } = useQuery({
    queryKey: ['employee-detail-release', releaseEmployeeId],
    queryFn: () => getEmployee(releaseEmployeeId),
    enabled: !!releaseEmployeeId,
  })

  const { data: occupiedSeats, isLoading: loadingOccupied } = useQuery({
    queryKey: ['occupied-seats', floor, zone],
    queryFn: () => getOccupiedSeats({ floor: floor || undefined, zone: zone || undefined, limit: 50 }),
  })

  const { data: reservedSeats, isLoading: loadingReserved } = useQuery({
    queryKey: ['reserved-seats', floor, zone],
    queryFn: () => getSeats({ floor: floor || undefined, zone: zone || undefined, status: 'reserved', limit: 50 }),
  })

  const { data: maintenanceSeats, isLoading: loadingMaintenance } = useQuery({
    queryKey: ['maintenance-seats', floor, zone],
    queryFn: () => getSeats({ floor: floor || undefined, zone: zone || undefined, status: 'maintenance', limit: 50 }),
  })

  const statusMutation = useMutation({
    mutationFn: ({ seatId, status }) => updateSeatStatus(seatId, { status }),
    onSuccess: (data) => {
      setMessage({ type: 'success', text: `Seat ${data.seat_number} is now ${data.status}.` })
      invalidateAll()
      queryClient.invalidateQueries({ queryKey: ['reserved-seats'] })
      queryClient.invalidateQueries({ queryKey: ['maintenance-seats'] })
    },
    onError: (err) => {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Status change failed' })
    },
  })

  const handleAllocate = (e) => {
    e.preventDefault()
    if (!selectedEmployeeId) {
      setMessage({ type: 'error', text: 'Select an employee first.' })
      return
    }
    if (!selectedProjectId && !selectedEmployeeDetail?.project_id) {
      setMessage({
        type: 'error',
        text: 'This employee has no project assigned yet — choose a project below before allocating a seat.',
      })
      return
    }
    allocateMutation.mutate({
      employee_id: Number(selectedEmployeeId),
      project_id: selectedProjectId ? Number(selectedProjectId) : undefined,
      preferred_floor: preferredFloor ? Number(preferredFloor) : undefined,
      preferred_zone: preferredZone ? preferredZone.trim() : undefined,
    })
  }

  const handleCsvUpload = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setCsvUploading(true)
    setCsvResult(null)
    try {
      const result = await uploadSeatsCSV(file)
      setCsvResult(result)
      invalidateAll()
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'CSV upload failed' })
    } finally {
      setCsvUploading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Seat Allocation</h1>
        <label className="bg-white border border-slate-300 text-slate-700 text-sm font-medium px-4 py-2 rounded-md hover:bg-slate-50 cursor-pointer">
          {csvUploading ? 'Uploading...' : 'Upload Seats CSV'}
          <input type="file" accept=".csv" className="hidden" disabled={csvUploading} onChange={handleCsvUpload} />
        </label>
      </div>

      {csvResult && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4 text-sm space-y-1">
          <div className="font-medium text-slate-700">
            CSV upload: {csvResult.created} created, {csvResult.skipped} skipped.
          </div>
          <p className="text-xs text-slate-400">
            Expected columns: floor, zone, seat_number (required), bay, status (optional -- defaults to available).
          </p>
          {csvResult.warnings.length > 0 && (
            <details className="text-xs text-amber-600">
              <summary className="cursor-pointer">{csvResult.warnings.length} warning(s)</summary>
              <ul className="list-disc pl-4 mt-1 space-y-0.5">
                {csvResult.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </details>
          )}
          {csvResult.errors.length > 0 && (
            <details className="text-xs text-rose-600">
              <summary className="cursor-pointer">{csvResult.errors.length} row(s) skipped</summary>
              <ul className="list-disc pl-4 mt-1 space-y-0.5">
                {csvResult.errors.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            </details>
          )}
        </div>
      )}

      {message && (
        <div
          className={`rounded-md px-4 py-2 text-sm ${
            message.type === 'success' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200'
          }`}
        >
          {message.text}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-6">
        <form onSubmit={handleAllocate} className="bg-white rounded-xl shadow-sm border border-slate-200 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-slate-700">Allocate a Seat</h2>

          <div>
            <label className="text-xs text-slate-500">Employee (name / email / code)</label>
            <input
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mt-1"
              placeholder="Start typing..."
              value={employeeQuery}
              onChange={(e) => {
                setEmployeeQuery(e.target.value)
                setSelectedEmployeeId('')
              }}
            />
            {employeeOptions?.length > 0 && !selectedEmployeeId && (
              <div className="border border-slate-200 rounded-md mt-1 max-h-40 overflow-y-auto bg-white shadow-sm">
                {employeeOptions.map((emp) => (
                  <div
                    key={emp.id}
                    className="px-3 py-2 text-sm hover:bg-slate-50 cursor-pointer"
                    onClick={() => {
                      setSelectedEmployeeId(String(emp.id))
                      setEmployeeQuery(`${emp.name} (${emp.employee_code})`)
                    }}
                  >
                    {emp.name} &middot; {emp.email} &middot; {emp.status}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="text-xs text-slate-500">
              Project{selectedEmployeeId && !selectedEmployeeDetail?.project_id ? (
                <span className="text-rose-600 font-medium"> (required — this employee has none yet)</span>
              ) : (
                " (optional — defaults to employee's assigned project)"
              )}
            </label>
            <select
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mt-1"
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
            >
              <option value="">
                {selectedEmployeeDetail?.project_name
                  ? `Use employee's current project (${selectedEmployeeDetail.project_name})`
                  : 'Select a project...'}
              </option>
              {projects?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500">
              Preferred floor / zone (optional — tries this first, falls back automatically if full)
            </label>
            <div className="flex gap-2 mt-1">
              <input
                type="number"
                className="w-1/2 border border-slate-300 rounded-md px-3 py-2 text-sm"
                placeholder="Floor, e.g. 2"
                value={preferredFloor}
                onChange={(e) => setPreferredFloor(e.target.value)}
              />
              <input
                type="text"
                className="w-1/2 border border-slate-300 rounded-md px-3 py-2 text-sm"
                placeholder="Zone, e.g. Z2"
                value={preferredZone}
                onChange={(e) => setPreferredZone(e.target.value)}
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={
              allocateMutation.isPending ||
              (!!selectedEmployeeId && !selectedProjectId && !selectedEmployeeDetail?.project_id)
            }
            className="bg-brand-600 text-white text-sm font-medium px-4 py-2 rounded-md hover:bg-brand-700 disabled:opacity-50"
          >
            {allocateMutation.isPending ? 'Allocating...' : 'Allocate Seat'}
          </button>
        </form>

        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-slate-700">Release a Seat</h2>
          <p className="text-xs text-slate-500">
            Find the employee by name, email, or employee code, then release their current seat.
          </p>

          <div>
            <label className="text-xs text-slate-500">Employee</label>
            <input
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mt-1"
              placeholder="Start typing..."
              value={releaseEmployeeQuery}
              onChange={(e) => {
                setReleaseEmployeeQuery(e.target.value)
                setReleaseEmployeeId('')
              }}
            />
            {releaseEmployeeOptions?.length > 0 && !releaseEmployeeId && (
              <div className="border border-slate-200 rounded-md mt-1 max-h-40 overflow-y-auto bg-white shadow-sm">
                {releaseEmployeeOptions.map((emp) => (
                  <div
                    key={emp.id}
                    className="px-3 py-2 text-sm hover:bg-slate-50 cursor-pointer"
                    onClick={() => {
                      setReleaseEmployeeId(String(emp.id))
                      setReleaseEmployeeQuery(`${emp.name} (${emp.employee_code})`)
                    }}
                  >
                    {emp.name} &middot; {emp.email} &middot; {emp.current_seat || 'Unallocated'}
                  </div>
                ))}
              </div>
            )}
          </div>

          {releaseEmployeeId && (
            <div className="text-xs rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
              {releaseEmployeeDetail?.current_seat
                ? <span>Currently seated at <span className="font-medium">{releaseEmployeeDetail.current_seat}</span>.</span>
                : <span className="text-amber-600">This employee has no active seat allocation.</span>}
            </div>
          )}

          <button
            type="button"
            disabled={!releaseEmployeeId || !releaseEmployeeDetail?.current_seat || releaseMutation.isPending}
            onClick={() => releaseMutation.mutate({ employee_id: Number(releaseEmployeeId) })}
            className="bg-rose-600 text-white text-sm font-medium px-4 py-2 rounded-md hover:bg-rose-700 disabled:opacity-50"
          >
            {releaseMutation.isPending ? 'Releasing...' : 'Release Seat'}
          </button>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-slate-700">Available Seats</h2>
          <div className="flex gap-2">
            <input
              className="border border-slate-300 rounded-md px-2 py-1 text-sm w-24"
              placeholder="Floor"
              value={floor}
              onChange={(e) => setFloor(e.target.value)}
            />
            <input
              className="border border-slate-300 rounded-md px-2 py-1 text-sm w-24"
              placeholder="Zone"
              value={zone}
              onChange={(e) => setZone(e.target.value)}
            />
          </div>
        </div>
        {loadingSeats ? (
          <div className="text-sm text-slate-500">Loading...</div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-2">
            {availableSeats.map((s) => (
              <div key={s.id} className="border border-emerald-200 bg-emerald-50 rounded-md px-2 py-2 text-xs text-center space-y-1">
                <div className="font-semibold text-emerald-700">{s.seat_number}</div>
                <div className="text-slate-500">
                  F{s.floor} &middot; {s.zone}
                </div>
                <select
                  className="w-full border border-emerald-300 rounded px-1 py-0.5 text-[11px] bg-white"
                  disabled={statusMutation.isPending}
                  value=""
                  onChange={(e) => {
                    if (e.target.value) statusMutation.mutate({ seatId: s.id, status: e.target.value })
                  }}
                >
                  <option value="">Mark as...</option>
                  <option value="reserved">Reserved</option>
                  <option value="maintenance">Maintenance</option>
                </select>
              </div>
            ))}
            {availableSeats.length === 0 && (
              <div className="text-sm text-slate-500 col-span-full">No available seats match this filter.</div>
            )}
          </div>
        )}
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
        <h2 className="text-sm font-semibold text-slate-700 mb-3">Currently Occupied Seats</h2>
        {loadingOccupied ? (
          <div className="text-sm text-slate-500">Loading...</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
            {occupiedSeats.map((s) => (
              <div
                key={s.id}
                className="border border-rose-200 bg-rose-50 rounded-md px-3 py-2 text-xs flex items-center justify-between gap-2"
              >
                <div>
                  <div className="font-semibold text-rose-700">{s.seat_number}</div>
                  <div className="text-slate-500">
                    F{s.floor} &middot; {s.zone} &middot; {s.occupied_by || 'Unknown'}
                  </div>
                  <div className="text-slate-400">
                    {s.occupied_by_project ? `Project: ${s.occupied_by_project}` : 'No project'}
                    {s.allocation_date && (
                      <> &middot; since {new Date(s.allocation_date).toLocaleDateString()}</>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  disabled={releaseMutation.isPending}
                  onClick={() => releaseMutation.mutate({ seat_id: s.id })}
                  className="text-rose-700 border border-rose-300 rounded-md px-2 py-1 hover:bg-rose-100 disabled:opacity-50 shrink-0"
                >
                  Release
                </button>
              </div>
            ))}
            {occupiedSeats.length === 0 && (
              <div className="text-sm text-slate-500 col-span-full">No occupied seats match this filter.</div>
            )}
          </div>
        )}
      </div>
<div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
        <h2 className="text-sm font-semibold text-slate-700 mb-1">Reserved & Maintenance Seats</h2>
        <p className="text-xs text-slate-500 mb-3">
          These seats can't be allocated until their status is changed back to Available.
        </p>
        {loadingReserved || loadingMaintenance ? (
          <div className="text-sm text-slate-500">Loading...</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
            {[...(reservedSeats || []), ...(maintenanceSeats || [])].map((s) => (
              <div
                key={s.id}
                className="border border-amber-200 bg-amber-50 rounded-md px-3 py-2 text-xs flex items-center justify-between gap-2"
              >
                <div>
                  <div className="font-semibold text-amber-700">{s.seat_number}</div>
                  <div className="text-slate-500">
                    F{s.floor} &middot; {s.zone} &middot; {s.status}
                  </div>
                </div>
                <select
                  className="border border-amber-300 rounded-md px-2 py-1 text-xs bg-white shrink-0"
                  disabled={statusMutation.isPending}
                  value=""
                  onChange={(e) => {
                    if (e.target.value) statusMutation.mutate({ seatId: s.id, status: e.target.value })
                  }}
                >
                  <option value="">Change status...</option>
                  <option value="available">Available</option>
                  {s.status !== 'maintenance' && <option value="maintenance">Maintenance</option>}
                  {s.status !== 'reserved' && <option value="reserved">Reserved</option>}
                </select>
              </div>
            ))}
            {(reservedSeats?.length || 0) + (maintenanceSeats?.length || 0) === 0 && (
              <div className="text-sm text-slate-500 col-span-full">No reserved or maintenance seats match this filter.</div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
