import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getProjects, getProjectEmployees, createProject, deleteProject } from '../api.js'

const emptyForm = { name: '', description: '', manager_name: '' }

export default function Projects() {
  const queryClient = useQueryClient()
  const [expandedId, setExpandedId] = useState(null)
  const [message, setMessage] = useState(null)
  const [form, setForm] = useState(emptyForm)
  const [showForm, setShowForm] = useState(false)

  const { data: projects, isLoading } = useQuery({ queryKey: ['projects'], queryFn: getProjects })

  const createMutation = useMutation({
    mutationFn: createProject,
    onSuccess: (data) => {
      setMessage({ type: 'success', text: `Project "${data.name}" created.` })
      setForm(emptyForm)
      setShowForm(false)
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
    onError: (err) => {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Could not create project' })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteProject,
    onSuccess: (data) => {
      setMessage({ type: 'success', text: data.detail })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] })
      queryClient.invalidateQueries({ queryKey: ['project-utilization'] })
    },
    onError: (err) => {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Could not delete project' })
    },
  })

  const handleDelete = (project) => {
    if (window.confirm(`Delete project "${project.name}"? If it still has employees or seat history, it will be hidden instead of removed.`)) {
      deleteMutation.mutate(project.id)
    }
  }

  const handleCreate = (e) => {
    e.preventDefault()
    if (!form.name) {
      setMessage({ type: 'error', text: 'Project name is required.' })
      return
    }
    createMutation.mutate({
      name: form.name,
      description: form.description || undefined,
      manager_name: form.manager_name || undefined,
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Projects</h1>
        <button
          type="button"
          onClick={() => setShowForm((v) => !v)}
          className="bg-brand-600 text-white text-sm font-medium px-4 py-2 rounded-md hover:bg-brand-700"
        >
          {showForm ? 'Cancel' : '+ Add Project'}
        </button>
      </div>

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
          <div>
            <label className="text-xs text-slate-500">Project Name *</label>
            <input
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mt-1"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div>
            <label className="text-xs text-slate-500">Manager Name</label>
            <input
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mt-1"
              value={form.manager_name}
              onChange={(e) => setForm({ ...form, manager_name: e.target.value })}
            />
          </div>
          <div>
            <label className="text-xs text-slate-500">Description</label>
            <input
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mt-1"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
          <div className="md:col-span-3">
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="bg-brand-600 text-white text-sm font-medium px-4 py-2 rounded-md hover:bg-brand-700 disabled:opacity-50"
            >
              {createMutation.isPending ? 'Creating...' : 'Create Project'}
            </button>
          </div>
        </form>
      )}

      {isLoading ? (
        <div className="text-sm text-slate-500">Loading...</div>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {projects.map((p) => (
            <div key={p.id} className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-semibold text-slate-800">{p.name}</div>
                  <div className="text-xs text-slate-500">Manager: {p.manager_name || '-'}</div>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    className="text-xs font-medium text-brand-600 hover:underline"
                    onClick={() => setExpandedId(expandedId === p.id ? null : p.id)}
                  >
                    {expandedId === p.id ? 'Hide team' : 'View team'}
                  </button>
                  <button
                    type="button"
                    disabled={deleteMutation.isPending}
                    onClick={() => handleDelete(p)}
                    className="text-xs font-medium text-slate-400 hover:text-rose-700 hover:underline disabled:opacity-50"
                    title="Deletes outright if unused, otherwise marks inactive and hides it"
                  >
                    Delete
                  </button>
                </div>
              </div>
              {expandedId === p.id && <ProjectTeam projectId={p.id} />}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ProjectTeam({ projectId }) {
  const { data: employees, isLoading } = useQuery({
    queryKey: ['project-employees', projectId],
    queryFn: () => getProjectEmployees(projectId),
  })

  if (isLoading) return <div className="text-xs text-slate-500 mt-3">Loading team...</div>

  return (
    <ul className="mt-3 text-sm space-y-1 max-h-48 overflow-y-auto border-t border-slate-100 pt-2">
      {employees.length === 0 && <li className="text-slate-400 text-xs">No employees assigned yet.</li>}
      {employees.map((e) => (
        <li key={e.id} className="flex justify-between text-slate-600">
          <span>{e.name}</span>
          <span className="text-xs text-slate-400">{e.current_seat || 'Unallocated'}</span>
        </li>
      ))}
    </ul>
  )
}
