import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { getDashboardSummary, getProjectUtilization, getFloorUtilization } from '../api.js'
import StatCard from '../components/StatCard.jsx'

export default function Dashboard() {
  const { data: summary, isLoading: loadingSummary } = useQuery({
    queryKey: ['dashboard-summary'],
    queryFn: getDashboardSummary,
  })
  const { data: projectUtil, isLoading: loadingProjects } = useQuery({
    queryKey: ['project-utilization'],
    queryFn: getProjectUtilization,
  })
  const { data: floorUtil, isLoading: loadingFloors } = useQuery({
    queryKey: ['floor-utilization'],
    queryFn: getFloorUtilization,
  })

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-slate-800">Dashboard</h1>

      {loadingSummary ? (
        <div className="text-slate-500 text-sm">Loading summary...</div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Total Employees" value={summary.total_employees.toLocaleString()} />
          <StatCard label="Total Seats" value={summary.total_seats.toLocaleString()} />
          <StatCard label="Occupied" value={summary.occupied_seats.toLocaleString()} accent="text-rose-600" />
          <StatCard label="Available" value={summary.available_seats.toLocaleString()} accent="text-emerald-600" />
          <StatCard label="Reserved" value={summary.reserved_seats.toLocaleString()} accent="text-amber-600" />
          <StatCard label="Maintenance" value={summary.maintenance_seats.toLocaleString()} accent="text-slate-500" />
          <StatCard
            label="New Joiners Pending"
            value={summary.new_joiners_pending.toLocaleString()}
            accent="text-brand-600"
          />
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
          <h2 className="text-sm font-semibold text-slate-700 mb-3">Project-wise Seat Allocation</h2>
          {loadingProjects ? (
            <div className="text-slate-500 text-sm">Loading...</div>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={projectUtil}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="project_name" tick={{ fontSize: 11 }} interval={0} angle={-30} textAnchor="end" height={60} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="seats_occupied" fill="#4f46e5" radius={[4, 4, 0, 0]} name="Seats Occupied" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
          <h2 className="text-sm font-semibold text-slate-700 mb-3">Floor-wise Occupancy</h2>
          {loadingFloors ? (
            <div className="text-slate-500 text-sm">Loading...</div>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={floorUtil}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="floor" tickFormatter={(f) => `Floor ${f}`} tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="occupied" stackId="a" fill="#e11d48" name="Occupied" />
                <Bar dataKey="available" stackId="a" fill="#10b981" name="Available" />
                <Bar dataKey="reserved" stackId="a" fill="#f59e0b" name="Reserved" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  )
}
