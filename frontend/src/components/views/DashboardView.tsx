import React from 'react';
import { HomeView } from './HomeView';

interface DashboardViewProps {
  onSelectProject: (projectId: string) => void;
  onNewProject: (presetBrief?: string, presetName?: string) => void;
  onViewProjects?: () => void;
  onViewBenchmarks?: () => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  onSelectProject,
  onNewProject,
  onViewProjects,
  onViewBenchmarks,
}) => {
  return (
    <HomeView
      onSelectProject={onSelectProject}
      onNewProject={() => onNewProject()}
      onViewProjects={onViewProjects || (() => {})}
      onViewBenchmarks={onViewBenchmarks}
    />
  );
};
