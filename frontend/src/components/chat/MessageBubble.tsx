import React from 'react';
import { QuestionCard } from './QuestionCard';
import type { QuestionCardData } from '../../api/types';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  time?: string;
  question_card?: QuestionCardData;
}

interface MessageBubbleProps {
  message: ChatMessage;
  isLatestAssistant?: boolean;
  onAnswerCard?: (answer: string) => void;
  disabled?: boolean;
  onOpenCustomPlot?: () => void;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({
  message,
  isLatestAssistant = false,
  onAnswerCard,
  disabled = false,
  onOpenCustomPlot,
}) => {
  const isUser = message.role === 'user';

  // Format simple markdown into HTML safely
  const renderFormattedText = (raw: string) => {
    // Split into paragraphs
    const paragraphs = raw.split('\n\n');
    return paragraphs.map((p, idx) => {
      // Check for bullet lists
      if (p.includes('\n• ') || p.startsWith('• ') || p.includes('\n- ') || p.startsWith('- ')) {
        const items = p.split(/\n[•\-]\s*/).filter(Boolean);
        return (
          <ul key={idx} style={{ margin: '0.35rem 0', paddingLeft: '1.25rem' }}>
            {items.map((it, iIdx) => (
              <li key={iIdx} dangerouslySetInnerHTML={{ __html: formatInline(it) }} />
            ))}
          </ul>
        );
      }

      // Check for headings
      if (p.startsWith('### ')) {
        return (
          <h3 key={idx} style={{ margin: '0.4rem 0', fontSize: '0.95rem', fontWeight: 700 }}>
            {p.replace('### ', '')}
          </h3>
        );
      }

      return (
        <p key={idx} style={{ margin: '0 0 0.4rem 0' }} dangerouslySetInnerHTML={{ __html: formatInline(p) }} />
      );
    });
  };

  const formatInline = (text: string) => {
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');
  };

  return (
    <div
      className={`chat-message-row ${message.role}`}
      data-testid={`chat-message-${message.role}`}
    >
      <div className="chat-message-avatar" aria-hidden="true">
        {isUser ? (
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <path d="M3 9h18" />
            <path d="M9 21V9" />
          </svg>
        )}
      </div>

      <div className="chat-message-content-wrapper">
        <div className="chat-bubble">
          {renderFormattedText(message.text)}
        </div>

        {/* Dynamic Question Card attached to this message */}
        {message.question_card && onAnswerCard && (
          <QuestionCard
            card={message.question_card}
            onAnswer={onAnswerCard}
            disabled={disabled || !isLatestAssistant}
            onOpenCustomPlot={onOpenCustomPlot}
          />
        )}

        {message.time && (
          <span className="chat-message-time">{message.time}</span>
        )}
      </div>
    </div>
  );
};
