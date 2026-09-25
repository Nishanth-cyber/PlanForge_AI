import React, { useRef, useEffect } from 'react';
import { MessageBubble, type ChatMessage } from './MessageBubble';
import { RequirementProgress } from './RequirementProgress';
import { ChatInput } from './ChatInput';
import { TypingIndicator } from './TypingIndicator';
import type { RequirementProgressItem } from '../../api/types';

interface ChatPanelProps {
  messages: ChatMessage[];
  progress: RequirementProgressItem[];
  remainingCount: number;
  isReadyForGeneration: boolean;
  isLoading: boolean;
  onSendMessage: (msg: string) => void;
  onResetConversation: () => void;
  projectName?: string;
  onOpenCustomPlot?: () => void;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  progress,
  remainingCount,
  isReadyForGeneration,
  isLoading,
  onSendMessage,
  onResetConversation,
  projectName = 'PlanForge AI',
  onOpenCustomPlot,
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to newest message
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  // Find index of latest assistant message
  let latestAssistantIndex = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'assistant') {
      latestAssistantIndex = i;
      break;
    }
  }

  return (
    <div className="chat-panel-container" data-testid="chat-panel">
      {/* 1. Header */}
      <header className="chat-header">
        <div className="chat-header-title">
          <div className="chat-header-avatar">P</div>
          <div className="chat-header-text">
            <h2>{projectName}</h2>
            <div className="chat-header-status">
              <span className="chat-status-dot" />
              <span>Conversational Architect</span>
            </div>
          </div>
        </div>

        <div className="chat-header-actions">
          <button
            className="btn btn-outline btn-sm"
            onClick={onResetConversation}
            title="Start fresh conversation"
            style={{ fontSize: '0.75rem', padding: '0.25rem 0.55rem' }}
          >
            ↻ Reset
          </button>
        </div>
      </header>

      {/* 2. Requirement Progress Section */}
      <RequirementProgress
        progress={progress}
        remainingCount={remainingCount}
        isReadyForGeneration={isReadyForGeneration}
      />

      {/* 3. Messages History */}
      <div className="chat-messages-container" ref={scrollRef}>
        {messages.map((msg, idx) => (
          <MessageBubble
            key={msg.id || idx}
            message={msg}
            isLatestAssistant={idx === latestAssistantIndex}
            onAnswerCard={onSendMessage}
            disabled={isLoading}
            onOpenCustomPlot={onOpenCustomPlot}
          />
        ))}

        {isLoading && (
          <div className="chat-message-row assistant">
            <div className="chat-message-avatar">P</div>
            <div className="chat-message-content-wrapper">
              <TypingIndicator />
            </div>
          </div>
        )}
      </div>

      {/* 4. Chat Input */}
      <ChatInput
        onSendMessage={onSendMessage}
        disabled={isLoading}
      />
    </div>
  );
};
