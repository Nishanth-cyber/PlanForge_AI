import React, { useState } from 'react';
import type { QuestionCardData } from '../../api/types';

interface QuestionCardProps {
  card: QuestionCardData;
  onAnswer: (answer: string) => void;
  disabled?: boolean;
  onOpenCustomPlot?: () => void;
}

export const QuestionCard: React.FC<QuestionCardProps> = ({
  card,
  onAnswer,
  disabled = false,
  onOpenCustomPlot,
}) => {
  const [selectedMulti, setSelectedMulti] = useState<string[]>([]);
  const [selectedSingle, setSelectedSingle] = useState<string | null>(null);
  const [customInput, setCustomInput] = useState<string>('');

  const isCustomPlotOption = (opt: string) => {
    const l = opt.toLowerCase();
    return l.includes('custom irregular') || l.includes('irregular plot');
  };

  const handleSingleClick = (option: string) => {
    if (disabled) return;
    if (isCustomPlotOption(option) && onOpenCustomPlot) {
      onOpenCustomPlot();
      return;
    }
    setSelectedSingle(option);
    onAnswer(option);
  };

  const handleToggleMulti = (option: string) => {
    if (disabled) return;
    setSelectedMulti((prev) =>
      prev.includes(option) ? prev.filter((o) => o !== option) : [...prev, option]
    );
  };

  const handleMultiSubmit = () => {
    if (disabled || selectedMulti.length === 0) return;
    const baseAnswer = selectedMulti.join(', ');
    const floorMatch = card.field_key?.match(/^floor_(\d+)_rooms$/);
    const answer =
      floorMatch && Number(floorMatch[1]) > 1
        ? `Floor ${floorMatch[1]}: ${baseAnswer}`
        : baseAnswer;
    onAnswer(answer);
  };

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (disabled || !customInput.trim()) return;
    onAnswer(customInput.trim());
    setCustomInput('');
  };

  return (
    <div className="question-card" data-testid="question-card" data-input-type={card.input_type}>
      <div className="question-card-title">
        <span>⚡</span>
        <span>{card.question}</span>
      </div>

      {/* 1. SINGLE CHOICE */}
      {card.input_type === 'single_choice' && (
        <div className="question-options-grid">
          {card.options.map((opt, idx) => (
            <button
              key={idx}
              className={`question-option-pill ${selectedSingle === opt ? 'selected' : ''}`}
              onClick={() => handleSingleClick(opt)}
              disabled={disabled}
              type="button"
            >
              {opt}
            </button>
          ))}
        </div>
      )}

      {/* 2. MULTI CHOICE */}
      {card.input_type === 'multi_choice' && (
        <div>
          <div className="question-options-grid" style={{ marginBottom: '0.65rem' }}>
            {card.options.map((opt, idx) => {
              const isSelected = selectedMulti.includes(opt);
              return (
                <button
                  key={idx}
                  className={`question-option-pill ${isSelected ? 'selected' : ''}`}
                  onClick={() => handleToggleMulti(opt)}
                  disabled={disabled}
                  type="button"
                  style={{
                    backgroundColor: isSelected ? 'var(--text-primary)' : 'var(--bg-surface)',
                    color: isSelected ? 'var(--text-inverse)' : 'var(--text-primary)',
                  }}
                >
                  <span style={{ fontSize: '0.8rem' }}>{isSelected ? '✓' : '+'}</span>{' '}
                  <span>{opt}</span>
                </button>
              );
            })}
          </div>

          <div className="multi-choice-footer">
            <span className="selected-counter">
              {selectedMulti.length} room{selectedMulti.length === 1 ? '' : 's'} selected
            </span>
            <button
              className="btn btn-primary btn-sm"
              onClick={handleMultiSubmit}
              disabled={disabled || selectedMulti.length === 0}
              type="button"
              style={{ padding: '0.35rem 0.85rem' }}
            >
              Continue →
            </button>
          </div>
        </div>
      )}

      {/* 3. DIRECTION (COMPASS) */}
      {card.input_type === 'direction' && (
        <div className="direction-grid">
          {card.options.map((dir, idx) => {
            const arrow =
              dir.toLowerCase().includes('north') ? '↑' :
              dir.toLowerCase().includes('south') ? '↓' :
              dir.toLowerCase().includes('east') ? '→' :
              dir.toLowerCase().includes('west') ? '←' : '•';
            return (
              <button
                key={idx}
                className={`direction-btn ${selectedSingle === dir ? 'selected' : ''}`}
                onClick={() => handleSingleClick(`Entrance facing ${dir}`)}
                disabled={disabled}
                type="button"
              >
                <span style={{ fontSize: '1.1rem' }}>{arrow}</span>{' '}
                <span>{dir}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* 4. NUMBER / CUSTOM DIMENSION */}
      {card.input_type === 'number' && (
        <div>
          {card.options && card.options.length > 0 && (
            <div className="question-options-grid" style={{ marginBottom: '0.5rem' }}>
              {card.options.map((opt, idx) => (
                <button
                  key={idx}
                  className="question-option-pill"
                  onClick={() => handleSingleClick(opt)}
                  disabled={disabled}
                  type="button"
                >
                  {opt}
                </button>
              ))}
            </div>
          )}
          <form onSubmit={handleCustomSubmit} style={{ display: 'flex', gap: '0.4rem' }}>
            <input
              type="text"
              className="form-control"
              placeholder="e.g. 40ft x 60ft or 250 sqm"
              value={customInput}
              onChange={(e) => setCustomInput(e.target.value)}
              disabled={disabled}
              style={{ fontSize: '0.825rem', padding: '0.35rem 0.6rem' }}
            />
            <button
              type="submit"
              className="btn btn-secondary btn-sm"
              disabled={disabled || !customInput.trim()}
            >
              Submit
            </button>
          </form>
        </div>
      )}

      {/* 5. CONFIRMATION */}
      {card.input_type === 'confirmation' && (
        <div className="confirmation-card-actions">
          <button
            className="btn-generate-confirm"
            onClick={() => handleSingleClick('Generate Floor Plan')}
            disabled={disabled}
            type="button"
            data-testid="confirm-generate-btn"
          >
            <span>✓</span>
            <span>Generate Floor Plan</span>
          </button>
          <button
            className="btn btn-outline btn-sm"
            onClick={() => handleSingleClick('Edit Requirements')}
            disabled={disabled}
            type="button"
            style={{ width: '100%', justifyContent: 'center' }}
          >
            ✏ Edit Requirements
          </button>
        </div>
      )}

      {/* 6. FREEFORM TEXT GUIDANCE */}
      {card.input_type === 'text' && (
        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
          Please type your response in the message bar below.
        </div>
      )}
    </div>
  );
};
