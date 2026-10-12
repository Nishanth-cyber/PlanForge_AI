import React from 'react';
import { QuestionCard } from './QuestionCard';
import type { QuestionCardData, QuickReplyItem, ChatActionData } from '../../api/types';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  time?: string;
  question_card?: QuestionCardData;
  response_type?: 'text' | 'quick_replies' | 'clarification' | 'requirement_summary' | 'generation_progress' | 'generation_result' | 'action_result' | string;
  intent?: string;
  conversation_stage?: string;
  quick_replies?: QuickReplyItem[];
  missing_requirements?: string[];
  requirements_updated?: string[];
  action?: ChatActionData;
  is_ready_for_generation?: boolean;
}

interface MessageBubbleProps {
  message: ChatMessage;
  isLatestAssistant?: boolean;
  onAnswerCard?: (answer: string) => void;
  onExecuteAction?: (action: ChatActionData) => void;
  disabled?: boolean;
  onOpenCustomPlot?: () => void;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({
  message,
  isLatestAssistant = false,
  onAnswerCard,
  onExecuteAction: _onExecuteAction,
  disabled = false,
  onOpenCustomPlot,
}) => {
  const isUser = message.role === 'user';
  const responseType = message.response_type || (message.question_card ? 'clarification' : 'text');

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

  // Render quick replies chips
  const renderQuickReplies = () => {
    const replies = message.quick_replies || [];
    if (replies.length === 0) {
      if (message.question_card && onAnswerCard) {
        return (
          <QuestionCard
            card={message.question_card}
            onAnswer={onAnswerCard}
            disabled={disabled || !isLatestAssistant}
            onOpenCustomPlot={onOpenCustomPlot}
          />
        );
      }
      return null;
    }

    return (
      <div className="quick-replies-container" data-testid="quick-replies">
        {replies.map((reply, idx) => (
          <button
            key={idx}
            className="quick-reply-btn"
            onClick={() => onAnswerCard?.(reply.value)}
            disabled={disabled || !isLatestAssistant}
            type="button"
          >
            {reply.label}
          </button>
        ))}
      </div>
    );
  };

  // Render Action Result Card (Exports, Validations)
  const renderActionResult = () => {
    const action = message.action;
    if (!action) return null;

    if (action.type === 'export') {
      const items = (action.payload?.items || []) as Array<{
        format: string;
        label: string;
        url: string | null;
        available: boolean;
        note: string;
      }>;

      const readyItems = items.filter((it) => it.available && it.url);

      return (
        <div className="chat-response-card" data-testid="export-action-card">
          <div className="chat-response-card-header">
            <span>📦 Export Artifacts</span>
            <span>{readyItems.length > 0 ? `${readyItems.length} Available` : 'Notice'}</span>
          </div>
          {readyItems.length > 0 ? (
            <div className="export-links-grid">
              {readyItems.map((item, idx) => (
                <a
                  key={idx}
                  href={item.url!}
                  download
                  className="export-download-btn"
                  target="_blank"
                  rel="noreferrer"
                  data-testid={`export-btn-${item.format}`}
                >
                  <span>⬇</span>
                  <span>{item.format.toUpperCase()}</span>
                </a>
              ))}
            </div>
          ) : (
            <div className="chat-response-card-body" style={{ color: 'var(--text-secondary)' }}>
              Export files become available once a floor plan design is generated.
            </div>
          )}
        </div>
      );
    }

    if (action.type === 'validation') {
      const val = action.payload?.validation;
      return (
        <div className="chat-response-card" data-testid="validation-action-card">
          <div className="chat-response-card-header">
            <span>🛡️ Validation Report</span>
            <span style={{ color: val?.overall_valid ? '#10b981' : '#f59e0b', fontWeight: 700 }}>
              {val?.overall_valid ? 'VALID' : 'NEEDS REVISION'}
            </span>
          </div>
          {val && (
            <div className="chat-response-card-body">
              <div><strong>Score:</strong> {val.overall_score}/100</div>
              <div><strong>Errors:</strong> {val.total_errors} • <strong>Warnings:</strong> {val.total_warnings}</div>
            </div>
          )}
        </div>
      );
    }

    return null;
  };

  // Render Generation Progress Card
  const renderGenerationProgress = () => {
    return (
      <div className="chat-response-card" data-testid="generation-progress-card">
        <div className="chat-response-card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <span className="progress-pulse-dot" />
            <span>Generation In Progress</span>
          </div>
          <span style={{ fontSize: '0.75rem', color: '#3b82f6' }}>Running</span>
        </div>
        <div className="chat-response-card-body" style={{ color: 'var(--text-secondary)' }}>
          Executing spatial allocation (ASAA), constraint solving, and CAD geometry synthesis...
        </div>
      </div>
    );
  };

  // Render Generation Result Card
  const renderGenerationResult = () => {
    const val = message.action?.payload?.validation;
    return (
      <div className="chat-response-card" data-testid="generation-result-card">
        <div className="chat-response-card-header">
          <span>✨ Design Generated</span>
          {val && (
            <span style={{ color: val.overall_valid ? '#10b981' : '#f59e0b', fontWeight: 700 }}>
              Score: {val.overall_score}/100
            </span>
          )}
        </div>
        <div className="chat-response-card-body">
          Floor plan generated and verified. Inspect the drawing on the workspace canvas.
        </div>
      </div>
    );
  };

  // Render Requirement Summary Card
  const renderRequirementSummary = () => {
    // If confirmation card exists, let QuestionCard render the buttons
    if (message.question_card && onAnswerCard) {
      return (
        <QuestionCard
          card={message.question_card}
          onAnswer={onAnswerCard}
          disabled={disabled || !isLatestAssistant}
          onOpenCustomPlot={onOpenCustomPlot}
        />
      );
    }

    if (message.is_ready_for_generation && onAnswerCard && isLatestAssistant) {
      return (
        <div className="chat-response-card" data-testid="requirement-summary-card">
          <div className="chat-response-card-header">
            <span>📋 Requirements Complete</span>
            <span style={{ color: '#10b981', fontWeight: 600 }}>Ready</span>
          </div>
          <div className="chat-response-card-actions">
            <button
              className="btn btn-primary btn-sm"
              onClick={() => onAnswerCard('Generate Floor Plan')}
              disabled={disabled}
              type="button"
            >
              ✓ Generate Floor Plan
            </button>
            <button
              className="btn btn-outline btn-sm"
              onClick={() => onAnswerCard('Edit Requirements')}
              disabled={disabled}
              type="button"
            >
              Edit Requirements
            </button>
          </div>
        </div>
      );
    }

    return null;
  };

  return (
    <div
      className={`chat-message-row ${message.role}`}
      data-testid={`chat-message-${message.role}`}
      data-response-type={responseType}
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

        {/* Conditional Component Rendering Based on Explicit Response Type (Section 2 & 7) */}
        {!isUser && (
          <>
            {responseType === 'quick_replies' && renderQuickReplies()}

            {responseType === 'clarification' && message.question_card && onAnswerCard && (
              <QuestionCard
                card={message.question_card}
                onAnswer={onAnswerCard}
                disabled={disabled || !isLatestAssistant}
                onOpenCustomPlot={onOpenCustomPlot}
              />
            )}

            {responseType === 'requirement_summary' && renderRequirementSummary()}

            {responseType === 'generation_progress' && renderGenerationProgress()}

            {responseType === 'generation_result' && renderGenerationResult()}

            {responseType === 'action_result' && renderActionResult()}

            {/* Fallback for legacy question cards when response_type not explicitly matched */}
            {!['text', 'quick_replies', 'clarification', 'requirement_summary', 'generation_progress', 'generation_result', 'action_result'].includes(responseType) &&
              message.question_card &&
              onAnswerCard && (
                <QuestionCard
                  card={message.question_card}
                  onAnswer={onAnswerCard}
                  disabled={disabled || !isLatestAssistant}
                  onOpenCustomPlot={onOpenCustomPlot}
                />
              )}
          </>
        )}

        {message.time && (
          <span className="chat-message-time">{message.time}</span>
        )}
      </div>
    </div>
  );
};

