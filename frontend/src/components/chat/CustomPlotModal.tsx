import React, { useState, useEffect } from 'react';
import { PlotEditor, type PlotData } from '../plot-editor/PlotEditor';

interface CustomPlotModalProps {
  isOpen: boolean;
  initialPlotData?: PlotData;
  onSave: (plotData: PlotData) => void;
  onCancel: () => void;
}

const DEFAULT_IRREGULAR_PLOT: PlotData = {
  mode: 'irregular',
  vertices: [
    [0, 0],
    [12, 0],
    [12, 8],
    [7, 10],
    [0, 8],
  ],
  width: 12,
  length: 10,
  unit: 'm',
  frontSetback: 2,
  rearSetback: 2,
  sideSetback: 2,
  orientation: 'north',
  isClosed: true,
};

export const CustomPlotModal: React.FC<CustomPlotModalProps> = ({
  isOpen,
  initialPlotData,
  onSave,
  onCancel,
}) => {
  const [plotData, setPlotData] = useState<PlotData>(() => {
    if (initialPlotData && initialPlotData.vertices) {
      return {
        ...initialPlotData,
        mode: 'irregular',
      };
    }
    return DEFAULT_IRREGULAR_PLOT;
  });

  const [isValid, setIsValid] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | undefined>(undefined);
  const [hasAttemptedSubmit, setHasAttemptedSubmit] = useState<boolean>(false);

  useEffect(() => {
    if (isOpen) {
      if (initialPlotData && initialPlotData.vertices) {
        setPlotData({
          ...initialPlotData,
          mode: 'irregular',
        });
        const tooFew = initialPlotData.vertices.length < 3;
        setIsValid(!tooFew);
        if (tooFew) {
          setErrorMessage('An irregular plot requires at least 3 vertices.');
        }
      }
      setHasAttemptedSubmit(false);
    }
  }, [isOpen, initialPlotData]);

  if (!isOpen) return null;

  const handleValidationChange = (valid: boolean, message?: string) => {
    setIsValid(valid);
    setErrorMessage(message);
  };

  const handleContinue = () => {
    setHasAttemptedSubmit(true);
    if (!isValid || plotData.vertices.length < 3 || !plotData.isClosed) {
      if (plotData.vertices.length < 3) {
        setErrorMessage('An irregular plot requires at least 3 vertices.');
      } else if (!plotData.isClosed) {
        setErrorMessage('Polygon boundary must be closed.');
      }
      setIsValid(false);
      return;
    }
    onSave(plotData);
  };

  return (
    <div
      className="custom-plot-modal-overlay"
      data-testid="custom-plot-modal"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        backgroundColor: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1.5rem',
      }}
    >
      <div
        className="card custom-plot-modal-card"
        style={{
          width: '95%',
          maxWidth: '1060px',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-strong)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: '0 20px 45px rgba(0, 0, 0, 0.4)',
          overflow: 'hidden',
        }}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '1.15rem 1.5rem',
            borderBottom: '1px solid var(--border-default)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            backgroundColor: 'var(--bg-surface)',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
              <span style={{ fontSize: '1.25rem' }}>📐</span>
              <h2 style={{ fontSize: '1.15rem', fontWeight: 700, margin: 0 }}>
                Custom Plot Dimensions
              </h2>
            </div>
            <p
              style={{
                fontSize: '0.825rem',
                color: 'var(--text-secondary)',
                margin: '0.2rem 0 0 1.9rem',
              }}
            >
              Define your plot boundary &bull; Shape: <strong>Irregular Polygon</strong>
            </p>
          </div>

          <button
            type="button"
            className="btn btn-outline btn-sm"
            onClick={onCancel}
            title="Close dialog without saving"
            data-testid="custom-plot-close-btn"
            style={{ fontSize: '0.9rem', padding: '0.25rem 0.6rem' }}
          >
            ✕
          </button>
        </div>

        {/* Modal Body: Authoritative PlotEditor */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '1.25rem',
            backgroundColor: 'var(--bg-primary)',
          }}
        >
          <PlotEditor
            plotData={plotData}
            onChange={(newData) => {
              setPlotData({
                ...newData,
                mode: 'irregular',
              });
            }}
            onValidationChange={handleValidationChange}
          />
        </div>

        {/* Modal Footer */}
        <div
          style={{
            padding: '1rem 1.5rem',
            borderTop: '1px solid var(--border-default)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            backgroundColor: 'var(--bg-surface)',
          }}
        >
          <div style={{ flex: 1, marginRight: '1rem' }}>
            {(!isValid || hasAttemptedSubmit) && errorMessage && (
              <div
                style={{
                  color: '#f87171',
                  fontSize: '0.825rem',
                  fontWeight: 500,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                }}
                data-testid="plot-validation-error"
              >
                <span>⚠️</span>
                <span>{errorMessage || 'Please define a valid closed plot boundary.'}</span>
              </div>
            )}
            {isValid && (
              <div
                style={{
                  color: 'var(--status-success)',
                  fontSize: '0.825rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                }}
              >
                <span>✓</span>
                <span>
                  Valid {plotData.vertices.length}-vertex irregular polygon ready to commit.
                </span>
              </div>
            )}
          </div>

          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              type="button"
              className="btn btn-outline"
              onClick={onCancel}
              data-testid="custom-plot-cancel-btn"
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleContinue}
              disabled={!isValid && hasAttemptedSubmit}
              data-testid="custom-plot-continue-btn"
            >
              Continue →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
