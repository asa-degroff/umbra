import {
  LayoutDashboard,
  Brain,
  Database,
  Calendar,
  Settings,
  Activity,
  Wifi,
  WifiOff,
  Radio,
  Compass
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'

interface SidebarProps {
  activeView: string
  onViewChange: (view: string) => void
  connectionStatus: 'connecting' | 'connected' | 'disconnected'
}

const menuItems = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'network', label: 'Network', icon: Radio },
  { id: 'frontier', label: 'Frontier', icon: Compass },
  { id: 'semantic', label: 'Semantic Analysis', icon: Brain },
  { id: 'records', label: 'Records', icon: Database },
  { id: 'tasks', label: 'Scheduled Tasks', icon: Calendar },
  { id: 'system', label: 'System', icon: Settings },
]

export default function Sidebar({ activeView, onViewChange, connectionStatus }: SidebarProps) {
  return (
    <div className="w-56 bg-card border-r flex flex-col">
      {/* Header */}
      <div className="p-4">
        <h1 className="text-lg font-semibold flex items-center gap-2">
          <Activity className="w-5 h-5 text-primary" />
          Umbra Dashboard
        </h1>
        <div className="flex items-center gap-2 mt-2">
          {connectionStatus === 'connected' ? (
            <Badge variant="success" className="gap-1">
              <Wifi className="w-3 h-3" />
              Connected
            </Badge>
          ) : connectionStatus === 'connecting' ? (
            <Badge variant="warning" className="gap-1">
              <Wifi className="w-3 h-3 animate-pulse" />
              Connecting
            </Badge>
          ) : (
            <Badge variant="destructive" className="gap-1">
              <WifiOff className="w-3 h-3" />
              Disconnected
            </Badge>
          )}
        </div>
      </div>

      <Separator />

      {/* Navigation */}
      <nav className="flex-1 p-2 space-y-1">
        {menuItems.map(item => (
          <Button
            key={item.id}
            variant={activeView === item.id ? 'secondary' : 'ghost'}
            className={cn(
              'w-full justify-start gap-3',
              activeView === item.id && 'bg-secondary'
            )}
            onClick={() => onViewChange(item.id)}
          >
            <item.icon className="w-4 h-4" />
            {item.label}
          </Button>
        ))}
      </nav>

      <Separator />

      {/* Footer */}
      <div className="p-4 text-xs text-muted-foreground">
        <div>Umbra Dashboard</div>
        <div>v0.1.0</div>
      </div>
    </div>
  )
}
