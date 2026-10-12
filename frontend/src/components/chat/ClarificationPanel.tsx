import React, { useState } from 'react';
import type { ClarificationOption, ClarificationRequest, FeasibilityType } from '../../api/types';

interface ClarificationPanelProps {
  projectId: string;
  clarification: ClarificationRequest;
  onSubmitResponse: (
    selectedOptionId?: string,
    responseText?: string,
    numericOverrides?: Record<string, number>
  ) => Promise<void>;
  onResume?: () => Promise<void>;
  onCancel?: () => Promise<void>;
  isSubmitting?: boolean;
  statusMessage?: string | null;
  stateVersion?: number;
}

export const ClarificationPanel: React.FC<ClarificationPanelProps> = ({
  projectId: _projectId,
  clarification,
  onSubmitResponse,
  onResume,
  onCancel,
  isSubmitting = false,
  statusMessage = null,
  stateVersion,
}) => {
  const [selectedOptionId, setSelectedOptionId] = useState<string>(
    clarification.options.length > 0 ? clarification.options[0].option_id : ''
  );
  const [customText, setCustomText] = useState<string>('');
  const [numericInputs, setNumericInputs] = useState<Record<string, number>>({});
  const [localError, setLocalError] = useState<string | null>(null);

  const handleOptionSelect = (option: ClarificationOption) => {
    setSelectedOptionId(option.option_id);
    if (option.numeric_changes) {
      setNumericInputs({ ...option.numeric_changes });
    }
  };

  const handleSubmit = async () => {
    setLocalError(null);
    if (!selectedOptionId && !customText.trim() && Object.keys(numericInputs).length === 0) {
      setLocalError('Please select an option or provide input to resolve this clarification.');
      return;
    }
    try {
      await onSubmitResponse(
        selectedOptionId || undefined,
        customText.trim() || undefined,
        Object.keys(numericInputs).length > 0 ? numericInputs : undefined
      );
    } catch (err: any) {
      setLocalError(err.message || 'Failed to submit response');
    }
  };

  const getFeasibilityBadge = (type: FeasibilityType) => {
    switch (type) {
      case 'verified_feasible':
        return (
          <span
            className="feasibility-badge verified"
            style={{
              fontSize: '0.72rem',
              fontWeight: 700,
              padding: '2px 8px',
              borderRadius: '12px',
              backgroundColor: '#e6f4ea',
              color: '#137333',
              border: '1px solid #ceead6',
            }}
          >
            ✓ Verified Feasible
          </span>
        );
      case 'suggested_alternative':
        return (
          <span
            className="feasibility-badge suggested"
            style={{
              fontSize: '0.72rem',
              fontWeight: 700,
              padding: '2px 8px',
              borderRadius: '12px',
              backgroundColor: '#e8f0fe',
              color: '#1a73e8',
              border: '1px solid #d2e3fc',
            }}
          >
            💡 Suggested Alternative (Pending Authorization)
          </span>
        );
      case 'unverified_hypothetical':
      default:
        return (
          <span
            className="feasibility-badge hypothetical"
            style={{
              fontSize: '0.72rem',
              fontWeight: 700,
              padding: '2px 8px',
              borderRadius: '12px',
              backgroundColor: '#fef7e0',
              color: '#b06000',
              border: '1px solid #feefc3',
            }}
          >
            ⚡ Unverified Hypothetical
          </span>
        );
    }
  };

  return (
    <div
      className="clarification-panel-container"
      data-testid="clarification-panel"
      style={{
        padding: '1.5rem',
        backgroundColor: 'var(--bg-card, #ffffff)',
        borderRadius: '8px',
        border: '1px solid var(--border-default, #e0e0e0)',
        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.08)',
        maxWidth: '720px',
        margin: '1.5rem auto',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <div>
          <span
            style={{
              fontSize: '0.75rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              color: '#d93025',
              letterSpacing: '0.5px',
            }}
          >
            Agentic Clarification Required
          </span>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 600, margin: '0.25rem 0 0 0' }}>
            {clarification.category.replace(/_/g, ' ')}
          </h2>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <span style={{ fontSize: '0.75rem', color: '#666', background: '#f1f3f4', padding: '3px 8px', borderRadius: '4px' }}>
            Version: {stateVersion ?? clarification.state_version}
          </span>
          <span style={{ fontSize: '0.75rem', color: '#666', background: '#f1f3f4', padding: '3px 8px', borderRadius: '4px' }}>
            ID: {clarification.request_id.slice(0, 10)}
          </span>
        </div>
      </div>

      {/* Question Prompt */}
      <div
        style={{
          padding: '1rem',
          backgroundColor: '#fff8e1',
          borderRadius: '6px',
          borderLeft: '4px solid #f9ab00',
          marginBottom: '1rem',
        }}
      >
        <p style={{ margin: 0, fontWeight: 500, fontSize: '0.95rem', color: '#3c4043' }}>
          {clarification.question}
        </p>
      </div>

      {/* Measured Deficit & Evidence */}
      {(clarification.measured_deficit_sqm != null || clarification.evidence) && (
        <div
          style={{
            padding: '0.85rem 1rem',
            backgroundColor: '#f8f9fa',
            borderRadius: '6px',
            border: '1px solid #e8eaed',
            marginBottom: '1.25rem',
          }}
        >
          {clarification.measured_deficit_sqm != null && (
            <div style={{ display: 'flex', gap: '1.5rem', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#5f6368', display: 'block' }}>Required Area</span>
                <span style={{ fontSize: '0.95rem', fontWeight: 600 }}>{clarification.required_sqm} m²</span>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#5f6368', display: 'block' }}>Available Area</span>
                <span style={{ fontSize: '0.95rem', fontWeight: 600 }}>{clarification.available_sqm} m²</span>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#d93025', display: 'block' }}>Measured Deficit</span>
                <span style={{ fontSize: '0.95rem', fontWeight: 700, color: '#d93025' }}>
                  -{clarification.measured_deficit_sqm} m²
                </span>
              </div>
            </div>
          )}
          {clarification.evidence && (
            <div style={{ fontSize: '0.85rem', color: '#5f6368', lineHeight: '1.4' }}>
              <strong>Evidence:</strong> {clarification.evidence}
            </div>
          )}
        </div>
      )}

      {/* Selectable Alternatives */}
      {clarification.options.length > 0 && (
        <div style={{ marginBottom: '1.25rem' }}>
          <label style={{ fontSize: '0.85rem', fontWeight: 600, display: 'block', marginBottom: '0.5rem' }}>
            Choose an Authorized Resolution Strategy:
          </label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
            {clarification.options.map((option) => {
              const isSelected = selectedOptionId === option.option_id;
              return (
                <div
                  key={option.option_id}
                  onClick={() => handleOptionSelect(option)}
                  data-testid={`clarification-option-${option.option_id}`}
                  style={{
                    padding: '0.85rem 1rem',
                    borderRadius: '6px',
                    border: isSelected ? '2px solid #1a73e8' : '1px solid #dadce0',
                    backgroundColor: isSelected ? '#f8fbff' : '#ffffff',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.35rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <input
                        type="radio"
                        name="clarification_opt"
                        checked={isSelected}
                        onChange={() => handleOptionSelect(option)}
                        style={{ cursor: 'pointer' }}
                      />
                      <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{option.title}</span>
                    </div>
                    {getFeasibilityBadge(option.feasibility_type)}
                  </div>
                  <p style={{ margin: '0 0 0.35rem 1.6rem', fontSize: '0.82rem', color: '#5f6368', lineHeight: '1.4' }}>
                    {option.description}
                  </p>
                  {option.affected_rooms && option.affected_rooms.length > 0 && (
                    <div style={{ marginLeft: '1.6rem', display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                      {option.affected_rooms.map((rm) => (
                        <span
                          key={rm}
                          style={{
                            fontSize: '0.7rem',
                            backgroundColor: '#e8eaed',
                            color: '#3c4043',
                            padding: '1px 6px',
                            borderRadius: '4px',
                          }}
                        >
                          {rm}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Free-text response if permitted */}
      {clarification.allow_free_text && (
        <div style={{ marginBottom: '1.25rem' }}>
          <label style={{ fontSize: '0.85rem', fontWeight: 600, display: 'block', marginBottom: '0.35rem' }}>
            Additional Instructions or Freeform Preference (Optional):
          </label>
          <textarea
            data-testid="clarification-free-text"
            value={customText}
            onChange={(e) => setCustomText(e.target.value)}
            placeholder="Type specific room adjustments, boundaries, or requirements here..."
            rows={2}
            style={{
              width: '100%',
              padding: '0.65rem',
              borderRadius: '6px',
              border: '1px solid #dadce0',
              fontSize: '0.85rem',
              fontFamily: 'inherit',
              resize: 'vertical',
            }}
          />
        </div>
      )}

      {/* Status or validation message */}
      {statusMessage && (
        <div
          data-testid="clarification-status-msg"
          style={{
            padding: '0.65rem 1rem',
            backgroundColor: '#e6f4ea',
            color: '#137333',
            borderRadius: '6px',
            fontSize: '0.85rem',
            marginBottom: '1rem',
          }}
        >
          {statusMessage}
        </div>
      )}
      {localError && (
        <div
          data-testid="clarification-error-msg"
          style={{
            padding: '0.65rem 1rem',
            backgroundColor: '#fce8e6',
            color: '#c5221f',
            borderRadius: '6px',
            fontSize: '0.85rem',
            marginBottom: '1rem',
          }}
        >
          {localError}
        </div>
      )}

      {/* Action Buttons */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
        {onCancel && (
          <button
            type="button"
            className="btn btn-outline"
            data-testid="clarification-cancel-btn"
            onClick={onCancel}
            disabled={isSubmitting}
            style={{
              padding: '0.5rem 1rem',
              fontSize: '0.85rem',
              borderRadius: '4px',
              cursor: 'pointer',
              border: '1px solid #dadce0',
              backgroundColor: '#fff',
            }}
          >
            Cancel Generation
          </button>
        )}
        <button
          type="button"
          className="btn btn-primary"
          data-testid="clarification-submit-btn"
          onClick={handleSubmit}
          disabled={isSubmitting}
          style={{
            padding: '0.5rem 1.25rem',
            fontSize: '0.85rem',
            fontWeight: 600,
            borderRadius: '4px',
            cursor: isSubmitting ? 'not-allowed' : 'pointer',
            backgroundColor: '#1a73e8',
            color: '#fff',
            border: 'none',
          }}
        >
          {isSubmitting ? 'Submitting...' : 'Authorize & Submit Revision'}
        </button>
        {onResume && (
          <button
            type="button"
            className="btn btn-success"
            data-testid="clarification-resume-btn"
            onClick={onResume}
            disabled={isSubmitting}
            style={{
              padding: '0.5rem 1.25rem',
              fontSize: '0.85rem',
              fontWeight: 600,
              borderRadius: '4px',
              cursor: 'pointer',
              backgroundColor: '#1e8e3e',
              color: '#fff',
              border: 'none',
            }}
          >
            Resume Workflow
          </button>
        )}
      </div>
    </div>
  );
};
