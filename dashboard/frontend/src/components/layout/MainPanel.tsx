import OverviewView from '../views/OverviewView'
import NetworkView from '../views/NetworkView'
import SemanticView from '../views/SemanticView'
import RecordsView from '../views/RecordsView'
import TasksView from '../views/TasksView'
import SystemView from '../views/SystemView'

interface MainPanelProps {
  activeView: string
}

export default function MainPanel({ activeView }: MainPanelProps) {
  const renderView = () => {
    switch (activeView) {
      case 'overview':
        return <OverviewView />
      case 'network':
        return <NetworkView />
      case 'semantic':
        return <SemanticView />
      case 'records':
        return <RecordsView />
      case 'tasks':
        return <TasksView />
      case 'system':
        return <SystemView />
      default:
        return <OverviewView />
    }
  }

  return (
    <div className="flex-1 overflow-auto p-6">
      {renderView()}
    </div>
  )
}
