import React from 'react';

export const TypingIndicator: React.FC = () => {
  return (
    <div className="typing-indicator" aria-label="AI is typing" data-testid="typing-indicator">
      <span className="typing-dot" />
      <span className="typing-dot" />
      <span className="typing-dot" />
    </div>
  );
};
