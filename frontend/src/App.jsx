import { NavLink, Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import EmployeeSearch from './pages/EmployeeSearch.jsx'
import SeatAllocation from './pages/SeatAllocation.jsx'
import Projects from './pages/Projects.jsx'
import AIAssistant from './pages/AIAssistant.jsx'

const navItems = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/employees', label: 'Employees' },
  { to: '/seats', label: 'Seat Allocation' },
  { to: '/projects', label: 'Projects' },
  { to: '/assistant', label: 'AI Assistant' },
]

function App() {
  return (
    <div className="min-h-screen">
      <header className="bg-brand-700 text-white sticky top-0 z-10 shadow">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="font-semibold text-lg tracking-tight">Ethara &middot; Seat Allocation</div>
          <nav className="flex gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    isActive ? 'bg-white text-brand-700' : 'text-brand-50 hover:bg-brand-600'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/employees" element={<EmployeeSearch />} />
          <Route path="/seats" element={<SeatAllocation />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/assistant" element={<AIAssistant />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
