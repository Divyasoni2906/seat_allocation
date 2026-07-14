import { useState } from 'react'
import { useQuery, useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getEmployees,
  createEmployee,
  deactivateEmployee,
  deleteEmployeePermanent,
  getProjects,
  uploadEmployeesCSV,
} from '../api.js'

const STATUS_OPTIONS = ['', 'active', 'inactive', 'pending']
const PAGE_SIZE = 50

const emptyForm = {
  employee_code: '',
  name: '',
  email: '',
  department: '',
  role: '',
  joining_date: '',
  project_id: '',
}

export default function EmployeeSearch() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [department, setDepartment] = useState('')
  const [message, setMessage] = useState(null)
  const [form, setForm] = useState(emptyForm)
  const [showForm, setShowForm] = useState(false)
  const [csvResult, setCsvResult] = useState(null)
  const [csvUploading, setCsvUploading] = useState(false)

  const {
    data,
    isLoading,
    isFetching,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['employees', search, status, department],
    queryFn: ({ pageParam = 0 }) =>
      getEmployees({
        search: search || undefined,
        status: status || undefined,
        department: department || undefined,
        limit: PAGE_SIZE,
        offset: pageParam,
      }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) =>
      lastPage.length === PAGE_SIZE ? allPages.length * PAGE_SIZE : undefined,
  })

  const employees = data?.pages.flat() ?? []
  const loadedCount = employees.length

  const { data: projects } = useQuery({ queryKey: ['projects'], queryFn: getProjects })

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['employees'] })
    queryClient.invalidateQueries({ queryKey: ['employee-options'] })
    queryClient.invalidateQueries({ queryKey: ['employee-options-release'] })
    queryClient.invalidateQueries({ queryKey: ['project-employees'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] })
    queryClient.invalidateQueries({ queryKey: ['project-utilization'] })
  }

  const createMutation = useMutation({
    mutationFn: createEmployee,
    onSuccess: (data) => {
      setMessage({
        type: 'success',
        text: `Added ${data.name} (${data.employee_code})${
          data.project_name ? ` to Project ${data.project_name}` : ' — no project assigned yet, pending allocation'
        }.`,
      })
      setForm(emptyForm)
      setShowForm(false)
      invalidateAll()
    },
    onError: (err) => {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Could not add employee' })
    },
  })

  const deactivateMutation = useMutation({
    mutationFn: deactivateEmployee,
    onSuccess: (data) => {
      setMessage({ type: 'success', text: data.detail })
      invalidateAll()
    },
    onError: (err) => {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Could not deactivate employee' })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteEmployeePermanent,
    onSuccess: (data) => {
      setMessage({ type: 'success', text: data.detail })
      invalidateAll()
    },
    onError: (err) => {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Could not delete employee' })
    },
  })

  const handleCreate = (e) => {
    e.preventDefault()
    if (!form.employee_code || !form.name || !form.email) {
      setMessage({ type: 'error', text: 'Employee code, name, and email are required.' })
      return
    }
    createMutation.mutate({
      employee_code: form.employee_code,
      name: form.name,
      email: form.email,
      department: form.department || undefined,
      role: form.role || undefined,
      joining_date: form.joining_date || undefined,
      project_id: form.project_id ? Number(form.project_id) : undefined,
    })
  }

  const handleCsvUpload = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = '' // allow re-selecting the same file later
    if (!file) return
    setCsvUploading(true)
    setCsvResult(null)
    try {
      const result = await uploadEmployeesCSV(file)
      setCsvResult(result)
      invalidateAll()
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'CSV upload failed' })
    } finally {
      setCsvUploading(false)
    }
  }

  const handleDelete = (emp) => {
    if (window.confirm(`Permanently delete ${emp.name}? This can't be undone. (Blocked automatically if they have any seat history.)`)) {
      deleteMutation.mutate(emp.id)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Employee Search</h1>
        <div className="flex gap-2">
          <label className="bg-white border border-slate-300 text-slate-700 text-sm font-medium px-4 py-2 rounded-md hover:bg-slate-50 cursor-pointer">
            {csvUploading ? 'Uploading...' : 'Upload CSV'}
            <input type="file" accept=".csv" className="hidden" disabled={csvUploading} onChange={handleCsvUpload} />
          </label>
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="bg-brand-600 text-white text-sm font-medium px-4 py-2 rounded-md hover:bg-brand-700"
          >
            {showForm ? 'Cancel' : '+ Add New Employee'}
          </button>
        </div>
      </div>

      {csvResult && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4 text-sm space-y-1">
          <div className="font-medium text-slate-700">
            CSV upload: {csvResult.created} created, {csvResult.skipped} skipped.
          </div>
          <p className="text-xs text-slate-400">
            Expected columns: employee_code, name, email (required), department, role, joining_date (YYYY-MM-DD), project_name (optional).
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

      {showForm && (
        <form onSubmit={handleCreate} className="bg-white rounded-xl shadow-sm border border-slate-200 p-4 grid md:grid-cols-3 gap-3">
          <h2 className="text-sm font-semibold text-slate-700 md:col-span-3">New Joiner Details</h2>

          <div>
            <label className="text-xs text-slate-500">Employee Code *</label>
            <input
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mt-1"
              value={form.employee_code}
              onChange={(e) => setForm({ ...form, employee_code: e.target.value })}
            />
          </div>
          <div>
            <label className="text-xs text-slate-500">Name *</label>
            <input
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mt-1"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div>
            <label className="text-xs text-slate-500">Email *</label>
            <input
              type="email"
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mt-1"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </div>
          <div>
            <label className="text-xs text-slate-500">Department</label>
            <input
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mt-1"
              value={form.department}
              onChange={(e) => setForm({ ...form, department: e.target.value })}
            />
          </div>
          <div>
            <label className="text-xs text-slate-500">Role</label>
            <input
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mt-1"
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
            />
          </div>
          <div>
            <label className="text-xs text-slate-500">Joining Date</label>
            <input
              type="date"
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mt-1"
              value={form.joining_date}
              onChange={(e) => setForm({ ...form, joining_date: e.target.value })}
            />
          </div>
          <div>
            <label className="text-xs text-slate-500">
              Project <span className="text-slate-400">(leave blank to keep as pending — allocate one later from the Seat Allocation tab)</span>
            </label>
            <select
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mt-1"
              value={form.project_id}
              onChange={(e) => setForm({ ...form, project_id: e.target.value })}
            >
              <option value="">No project yet (pending)</option>
              {projects?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>

          <div className="md:col-span-3">
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="bg-brand-600 text-white text-sm font-medium px-4 py-2 rounded-md hover:bg-brand-700 disabled:opacity-50"
            >
              {createMutation.isPending ? 'Adding...' : 'Add Employee'}
            </button>
          </div>
        </form>
      )}

      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4 flex flex-wrap gap-3">
        <input
          className="border border-slate-300 rounded-md px-3 py-2 text-sm flex-1 min-w-[200px]"
          placeholder="Search name, email, or employee code..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="border border-slate-300 rounded-md px-3 py-2 text-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s ? s[0].toUpperCase() + s.slice(1) : 'All statuses'}
            </option>
          ))}
        </select>
        <input
          className="border border-slate-300 rounded-md px-3 py-2 text-sm"
          placeholder="Department"
          value={department}
          onChange={(e) => setDepartment(e.target.value)}
        />
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-100 text-slate-600 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-4 py-2">Code</th>
              <th className="text-left px-4 py-2">Name</th>
              <th className="text-left px-4 py-2">Email</th>
              <th className="text-left px-4 py-2">Department</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Project</th>
              <th className="text-left px-4 py-2">Seat</th>
              <th className="text-left px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td className="px-4 py-6 text-slate-500" colSpan={8}>
                  Loading employees...
                </td>
              </tr>
            ) : employees.length === 0 ? (
              <tr>
                <td className="px-4 py-6 text-slate-500" colSpan={8}>
                  No employees match this filter.
                </td>
              </tr>
            ) : (
              employees.map((e) => (
                <tr key={e.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-2 font-mono text-xs">{e.employee_code}</td>
                  <td className="px-4 py-2 font-medium">{e.name}</td>
                  <td className="px-4 py-2 text-slate-500">{e.email}</td>
                  <td className="px-4 py-2">{e.department || '-'}</td>
                  <td className="px-4 py-2">
                    <StatusBadge status={e.status} />
                  </td>
                  <td className="px-4 py-2">{e.project_name || '-'}</td>
                  <td className="px-4 py-2 text-slate-500">{e.current_seat || 'Unallocated'}</td>
                  <td className="px-4 py-2 space-x-2 whitespace-nowrap">
                    {e.status !== 'inactive' && (
                      <button
                        type="button"
                        disabled={deactivateMutation.isPending}
                        onClick={() => deactivateMutation.mutate(e.id)}
                        className="text-xs text-rose-600 hover:underline disabled:opacity-50"
                        title="Marks the employee inactive and releases their seat, if any"
                      >
                        Deactivate
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={deleteMutation.isPending}
                      onClick={() => handleDelete(e)}
                      className="text-xs text-slate-400 hover:text-rose-700 hover:underline disabled:opacity-50"
                      title="Permanently deletes the record. Blocked if they have any seat allocation history."
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between">
        <div className="text-xs text-slate-400">
          {loadedCount > 0 && `Showing ${loadedCount} employee${loadedCount === 1 ? '' : 's'}${hasNextPage ? '+' : ''}`}
          {isFetching && !isLoading && !isFetchingNextPage && ' · Refreshing...'}
        </div>
        {hasNextPage && (
          <button
            type="button"
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
            className="bg-white border border-slate-300 text-slate-700 text-sm font-medium px-4 py-2 rounded-md hover:bg-slate-50 disabled:opacity-50"
          >
            {isFetchingNextPage ? 'Loading...' : 'Load More'}
          </button>
        )}
      </div>
    </div>
  )
}

function StatusBadge({ status }) {
  const styles = {
    active: 'bg-emerald-100 text-emerald-700',
    inactive: 'bg-slate-200 text-slate-600',
    pending: 'bg-amber-100 text-amber-700',
  }
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${styles[status] || ''}`}>{status}</span>
  )
}
