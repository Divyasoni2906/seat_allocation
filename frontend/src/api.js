import axios from 'axios'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// ---- Employees ----
export const getEmployees = (params) => api.get('/employees', { params }).then((r) => r.data)
export const getEmployee = (id) => api.get(`/employees/${id}`).then((r) => r.data)
export const createEmployee = (payload) => api.post('/employees', payload).then((r) => r.data)
export const updateEmployee = (id, payload) => api.put(`/employees/${id}`, payload).then((r) => r.data)
export const deactivateEmployee = (id) => api.delete(`/employees/${id}`).then((r) => r.data)
export const deleteEmployeePermanent = (id) => api.delete(`/employees/${id}/permanent`).then((r) => r.data)
export const uploadEmployeesCSV = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/employees/upload-csv', formData).then((r) => r.data)
}

// ---- Projects ----
export const getProjects = () => api.get('/projects').then((r) => r.data)
export const createProject = (payload) => api.post('/projects', payload).then((r) => r.data)
export const deleteProject = (id) => api.delete(`/projects/${id}`).then((r) => r.data)
export const getProjectEmployees = (id) => api.get(`/projects/${id}/employees`).then((r) => r.data)

// ---- Seats ----
export const getSeats = (params) => api.get('/seats', { params }).then((r) => r.data)
export const getOccupiedSeats = (params) => api.get('/seats', { params: { ...params, status: 'occupied' } }).then((r) => r.data)
export const getAvailableSeats = (params) => api.get('/seats/available', { params }).then((r) => r.data)
export const allocateSeat = (payload) => api.post('/seats/allocate', payload).then((r) => r.data)
export const releaseSeat = (payload) => api.post('/seats/release', payload).then((r) => r.data)
export const updateSeatStatus = (seatId, payload) => api.patch(`/seats/${seatId}/status`, payload).then((r) => r.data)
export const uploadSeatsCSV = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/seats/upload-csv', formData).then((r) => r.data)
}

// ---- Dashboard ----
export const getDashboardSummary = () => api.get('/dashboard/summary').then((r) => r.data)
export const getProjectUtilization = () => api.get('/dashboard/project-utilization').then((r) => r.data)
export const getFloorUtilization = () => api.get('/dashboard/floor-utilization').then((r) => r.data)

// ---- AI Assistant ----
export const askAI = (query) => api.post('/ai/query', { query }).then((r) => r.data)