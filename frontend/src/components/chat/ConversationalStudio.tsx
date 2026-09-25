import React, { useState, useEffect, useCallback } from 'react';
import { ChatPanel } from './ChatPanel';
import { FloorPlanWorkspace } from './FloorPlanWorkspace';
import { type ChatMessage } from './MessageBubble';
import { CustomPlotModal } from './CustomPlotModal';
import { type PlotData } from '../plot-editor/PlotEditor';
import { sendChatTurn } from '../../api/projects';
import type {
  RequirementProgressItem,
  ProjectData,
  GenerationResponse,
  GeoRoom,
  GenerationRequest,
} from '../../api/types';

interface ConversationalStudioProps {
  initialBrief?: string;
  initialProjectName?: string;
  isGenerating: boolean;
  projectData: ProjectData | null;
  generationResponse: GenerationResponse | null;
  onGenerateSubmit: (req: GenerationRequest) => Promise<void>;
  activeFloor: number;
  onSelectFloor: (floor: number) => void;
  selectedAlternativeIndex: number;
  onSelectAlternative: (index: number) => void;
  selectedRoom: GeoRoom | null;
  onSelectRoom: (room: GeoRoom | null) => void;
  theme?: 'light' | 'dark';
  onViewTrace?: () => void;
  onViewExports?: () => void;
}

export const ConversationalStudio: React.FC<ConversationalStudioProps> = ({
  initialBrief,
  initialProjectName,
  isGenerating,
  projectData,
  generationResponse,
  onGenerateSubmit,
  activeFloor,
  onSelectFloor,
  selectedAlternativeIndex,
  onSelectAlternative,
  selectedRoom,
  onSelectRoom,
  theme = 'light',
  onViewTrace,
  onViewExports,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [progress, setProgress] = useState<RequirementProgressItem[]>([]);
  const [remainingCount, setRemainingCount] = useState<number>(5);
  const [isReadyForGeneration, setIsReadyForGeneration] = useState<boolean>(false);
  const [canonicalBrief, setCanonicalBrief] = useState<string>(initialBrief || '');
  const [projectName, setProjectName] = useState<string>(initialProjectName || 'PlanForge Residential Project');
  const [isLoadingChat, setIsLoadingChat] = useState<boolean>(false);
  const [isCustomPlotModalOpen, setIsCustomPlotModalOpen] = useState<boolean>(false);
  const [savedPlotData, setSavedPlotData] = useState<PlotData | undefined>(undefined);

  // Initialize conversation
  const initConversation = useCallback(async (starterBrief?: string) => {
    setIsLoadingChat(true);
    try {
      if (starterBrief && starterBrief.trim()) {
        // Pre-loaded prompt (e.g. from benchmarks)
        const resp = await sendChatTurn({
          message: starterBrief,
          project_name: projectName,
        });

        const initialMsgs: ChatMessage[] = [
          {
            id: 'init-user',
            role: 'user',
            text: starterBrief,
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
          {
            id: 'init-ai',
            role: 'assistant',
            text: resp.message,
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            question_card: resp.question_card,
          },
        ];

        setMessages(initialMsgs);
        setProgress(resp.progress || []);
        setRemainingCount(resp.remaining_count || 0);
        setIsReadyForGeneration(resp.is_ready_for_generation);
        setCanonicalBrief(resp.requirements_text || starterBrief);
      } else {
        // Standard initial greeting
        const resp = await sendChatTurn({
          message: '',
          project_name: projectName,
        });

        const initialAiMsg: ChatMessage = {
          id: 'welcome-ai',
          role: 'assistant',
          text: resp.message,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          question_card: resp.question_card,
        };

        setMessages([initialAiMsg]);
        setProgress(resp.progress || []);
        setRemainingCount(resp.remaining_count || 5);
        setIsReadyForGeneration(false);
        setCanonicalBrief('');
      }
    } catch (err) {
      console.error('Failed to initialize conversation', err);
      setMessages([
        {
          id: 'err-ai',
          role: 'assistant',
          text: 'Hello! I am PlanForge AI. You can describe your building requirements to get started.',
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setIsLoadingChat(false);
    }
  }, [projectName]);

  useEffect(() => {
    initConversation(initialBrief);
  }, [initConversation, initialBrief]);

  // Handle user sending text or answering a question card
  const handleOpenCustomPlot = () => {
    setIsCustomPlotModalOpen(true);
  };

  const handleCustomPlotSubmit = async (plot: PlotData) => {
    setIsCustomPlotModalOpen(false);
    setSavedPlotData(plot);

    // Format coordinates in meters
    const coordsStr = plot.vertices.map(([x, y]) => `(${Number(x).toFixed(1)}, ${Number(y).toFixed(1)})`).join(', ');
    const plotBriefSnippet = `Plot polygon: ${coordsStr} facing ${plot.orientation} with front setback: ${plot.frontSetback}m, rear setback: ${plot.rearSetback}m, side setback: ${plot.sideSetback}m.`;

    // Compact user message in chat: "Custom irregular plot defined."
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      text: 'Custom irregular plot defined.',
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoadingChat(true);

    try {
      const resp = await sendChatTurn({
        message: plotBriefSnippet,
        existing_brief: canonicalBrief,
        project_name: projectName,
      });

      const aiReply: ChatMessage = {
        id: `ai-${Date.now()}`,
        role: 'assistant',
        text: resp.message,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        question_card: resp.question_card,
      };

      setMessages((prev) => [...prev, aiReply]);
      setProgress(resp.progress || []);
      setRemainingCount(resp.remaining_count || 0);
      setIsReadyForGeneration(resp.is_ready_for_generation);
      if (resp.requirements_text) {
        setCanonicalBrief(resp.requirements_text);
      }
      if (resp.project_name) {
        setProjectName(resp.project_name);
      }
    } catch (err: any) {
      console.error('Chat turn failed for custom plot', err);
      const errReply: ChatMessage = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        text: `Sorry, I encountered an issue saving your custom plot: ${err.message || 'Unknown error'}. Please try again.`,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errReply]);
    } finally {
      setIsLoadingChat(false);
    }
  };

  const handleSendMessage = async (userText: string) => {
    const cleanText = userText.trim();
    if (!cleanText || isLoadingChat || isGenerating) return;

    // Check if user requested custom irregular plot via chat message
    const isCustomPlotRequest =
      cleanText.toLowerCase().includes('custom irregular plot') ||
      cleanText.toLowerCase() === 'custom irregular plot' ||
      cleanText.toLowerCase() === 'irregular plot';

    if (isCustomPlotRequest) {
      setIsCustomPlotModalOpen(true);
      return;
    }

    // 1. If user clicks "Generate Floor Plan" confirmation
    if (
      cleanText.toLowerCase().includes('generate floor plan') ||
      cleanText.toLowerCase() === 'generate' ||
      cleanText === '✓ Generate Floor Plan'
    ) {
      // Add user message
      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        text: 'Generate Floor Plan',
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      const aiMsg: ChatMessage = {
        id: `ai-${Date.now() + 1}`,
        role: 'assistant',
        text: 'Starting generation pipeline! Executing spatial allocation (ASAA), architectural intent synthesis, CAD geometry construction, and independent code validation...',
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, userMsg, aiMsg]);

      // Trigger authoritative generation through existing pipeline
      await onGenerateSubmit({
        brief: canonicalBrief,
        project_name: projectName,
        num_alternatives: 3,
        enable_refinement: true,
        max_refinement_iterations: 5,
        enable_rendering: true,
        enable_exports: true,
        create_zip: false,
        plot_shape: savedPlotData?.vertices,
      });

      return;
    }

    // 2. Normal conversational turn (text or card choice)
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      text: cleanText,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoadingChat(true);

    try {
      const resp = await sendChatTurn({
        message: cleanText,
        existing_brief: canonicalBrief,
        project_name: projectName,
      });

      const aiReply: ChatMessage = {
        id: `ai-${Date.now()}`,
        role: 'assistant',
        text: resp.message,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        question_card: resp.question_card,
      };

      setMessages((prev) => [...prev, aiReply]);
      setProgress(resp.progress || []);
      setRemainingCount(resp.remaining_count || 0);
      setIsReadyForGeneration(resp.is_ready_for_generation);
      if (resp.requirements_text) {
        setCanonicalBrief(resp.requirements_text);
      }
      if (resp.project_name) {
        setProjectName(resp.project_name);
      }
    } catch (err: any) {
      console.error('Chat turn failed', err);
      const errReply: ChatMessage = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        text: `Sorry, I encountered an issue: ${err.message || 'Unknown error'}. Please try again.`,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errReply]);
    } finally {
      setIsLoadingChat(false);
    }
  };

  const handleReset = () => {
    initConversation(undefined);
  };

  return (
    <div className="conversational-studio" data-testid="conversational-studio">
      {/* LEFT PANEL: Conversational PlanForge AI Assistant */}
      <ChatPanel
        messages={messages}
        progress={progress}
        remainingCount={remainingCount}
        isReadyForGeneration={isReadyForGeneration}
        isLoading={isLoadingChat}
        onSendMessage={handleSendMessage}
        onResetConversation={handleReset}
        projectName={projectName}
        onOpenCustomPlot={handleOpenCustomPlot}
      />

      {/* RIGHT PANEL: Floor-plan Visualization / Canvas Workspace */}
      <FloorPlanWorkspace
        isGenerating={isGenerating}
        projectData={projectData}
        generationResponse={generationResponse}
        activeFloor={activeFloor}
        onSelectFloor={onSelectFloor}
        selectedAlternativeIndex={selectedAlternativeIndex}
        onSelectAlternative={onSelectAlternative}
        selectedRoom={selectedRoom}
        onSelectRoom={onSelectRoom}
        theme={theme}
        onViewTrace={onViewTrace}
        onViewExports={onViewExports}
      />

      {/* MODAL: Custom Irregular Plot Editor Popup */}
      <CustomPlotModal
        isOpen={isCustomPlotModalOpen}
        initialPlotData={savedPlotData}
        onSave={handleCustomPlotSubmit}
        onCancel={() => setIsCustomPlotModalOpen(false)}
      />
    </div>
  );
};
