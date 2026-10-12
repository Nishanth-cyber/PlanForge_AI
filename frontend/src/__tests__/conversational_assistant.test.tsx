import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QuestionCard } from '../components/chat/QuestionCard';
import { RequirementProgress } from '../components/chat/RequirementProgress';
import { ChatInput } from '../components/chat/ChatInput';
import { ConversationalStudio } from '../components/chat/ConversationalStudio';
import * as projectApi from '../api/projects';

describe('Conversational AI Floor-Plan Assistant UI', () => {
  it('renders single_choice question card and triggers onAnswer when clicked', () => {
    const onAnswer = vi.fn();
    render(
      <QuestionCard
        card={{
          question: 'How many floors do you need?',
          input_type: 'single_choice',
          options: ['1 Floor', '2 Floors', '3 Floors'],
          field_key: 'target_floors',
        }}
        onAnswer={onAnswer}
      />
    );

    expect(screen.getByText(/How many floors do you need\?/i)).toBeDefined();
    const optBtn = screen.getByRole('button', { name: /2 Floors/i });
    expect(optBtn).toBeDefined();

    fireEvent.click(optBtn);
    expect(onAnswer).toHaveBeenCalledWith('2 Floors');
  });

  it('renders multi_choice card and submits selected items on Continue', () => {
    const onAnswer = vi.fn();
    render(
      <QuestionCard
        card={{
          question: 'Select rooms for Floor 1:',
          input_type: 'multi_choice',
          options: ['Living Room', 'Kitchen', 'Dining Room', 'Master Bedroom'],
          field_key: 'floor_1_rooms',
        }}
        onAnswer={onAnswer}
      />
    );

    const livingBtn = screen.getByRole('button', { name: /\+ Living Room/i });
    const kitchenBtn = screen.getByRole('button', { name: /\+ Kitchen/i });
    const continueBtn = screen.getByRole('button', { name: /Continue →/i });

    // Click rooms
    fireEvent.click(livingBtn);
    fireEvent.click(kitchenBtn);

    expect(screen.getByText(/2 rooms selected/i)).toBeDefined();

    // Click Continue
    fireEvent.click(continueBtn);
    expect(onAnswer).toHaveBeenCalledWith('Living Room, Kitchen');
  });

  it('renders direction compass card and triggers onAnswer with facing direction', () => {
    const onAnswer = vi.fn();
    render(
      <QuestionCard
        card={{
          question: 'Select entrance facing direction:',
          input_type: 'direction',
          options: ['North', 'South', 'East', 'West'],
          field_key: 'entrance_facing',
        }}
        onAnswer={onAnswer}
      />
    );

    const northBtn = screen.getByRole('button', { name: /↑ North/i });
    fireEvent.click(northBtn);
    expect(onAnswer).toHaveBeenCalledWith('Entrance facing North');
  });

  it('renders confirmation card with Generate Floor Plan button', () => {
    const onAnswer = vi.fn();
    render(
      <QuestionCard
        card={{
          question: 'Ready to generate?',
          input_type: 'confirmation',
          options: ['Generate Floor Plan', 'Edit Requirements'],
          field_key: 'confirmation',
        }}
        onAnswer={onAnswer}
      />
    );

    const genBtn = screen.getByTestId('confirm-generate-btn');
    expect(genBtn).toBeDefined();

    fireEvent.click(genBtn);
    expect(onAnswer).toHaveBeenCalledWith('Generate Floor Plan');
  });

  it('renders requirement progress section with completed and pending items', () => {
    const progress = [
      { name: 'Project type', status: 'completed', value: 'Residential' },
      { name: 'Plot dimensions', status: 'completed', value: '12.2m × 15.2m' },
      { name: 'Floors', status: 'completed', value: '2 Floors' },
      { name: 'Entrance orientation', status: 'current' },
      { name: 'Floor 1 rooms', status: 'pending' },
      { name: 'Floor 2 rooms', status: 'pending' },
    ];

    render(
      <RequirementProgress
        progress={progress}
        remainingCount={3}
        isReadyForGeneration={false}
      />
    );

    expect(screen.getByText(/Building Requirements/i)).toBeDefined();
    expect(screen.getByText(/3 requirements remaining/i)).toBeDefined();
    expect(screen.getByText(/Residential/i)).toBeDefined();
    expect(screen.getByText(/12.2m × 15.2m/i)).toBeDefined();
  });

  it('renders ChatInput and submits user typed text', () => {
    const onSendMessage = vi.fn();
    render(<ChatInput onSendMessage={onSendMessage} />);

    const textarea = screen.getByTestId('chat-input-textarea');
    fireEvent.change(textarea, { target: { value: 'I want a 2 bedroom bungalow' } });

    const sendBtn = screen.getByTestId('chat-send-btn');
    fireEvent.click(sendBtn);

    expect(onSendMessage).toHaveBeenCalledWith('I want a 2 bedroom bungalow');
  });

  it('renders ConversationalStudio two-panel interface', async () => {
    vi.spyOn(projectApi, 'sendChatTurn').mockResolvedValue({
      message: 'Hello! I am PlanForge AI. What type of project are you planning?',
      question_card: {
        question: 'What type of project are you planning?',
        input_type: 'single_choice',
        options: ['Residential House', 'Duplex'],
        field_key: 'project_type',
      },
      is_ready_for_generation: false,
      requirements_text: '',
      progress: [{ name: 'Project type', status: 'current' }],
      remaining_count: 5,
      project_name: 'My Project',
      status: 'INITIAL',
    });

    const onGenerateSubmit = vi.fn();
    const onSelectFloor = vi.fn();
    const onSelectAlternative = vi.fn();
    const onSelectRoom = vi.fn();

    render(
      <ConversationalStudio
        isGenerating={false}
        projectData={null}
        generationResponse={null}
        onGenerateSubmit={onGenerateSubmit}
        activeFloor={1}
        onSelectFloor={onSelectFloor}
        selectedAlternativeIndex={1}
        onSelectAlternative={onSelectAlternative}
        selectedRoom={null}
        onSelectRoom={onSelectRoom}
      />
    );

    expect(screen.getByTestId('conversational-studio')).toBeDefined();
    expect(screen.getByTestId('chat-panel')).toBeDefined();
    expect(screen.getByTestId('floor-plan-workspace')).toBeDefined();
    expect(screen.getByText(/Your floor plan will appear here/i)).toBeDefined();
  });

  it('QuestionCard intercepts "Custom Irregular Plot" and calls onOpenCustomPlot without sending onAnswer', () => {
    const onAnswer = vi.fn();
    const onOpenCustomPlot = vi.fn();

    render(
      <QuestionCard
        card={{
          question: 'What are the dimensions or total area of your plot?',
          input_type: 'single_choice',
          options: [
            '30ft x 40ft (1,200 sq ft)',
            '40ft x 50ft (2,000 sq ft)',
            'Custom Irregular Plot',
          ],
          field_key: 'plot_dimensions',
        }}
        onAnswer={onAnswer}
        onOpenCustomPlot={onOpenCustomPlot}
      />
    );

    const customBtn = screen.getByRole('button', { name: /Custom Irregular Plot/i });
    expect(customBtn).toBeDefined();

    fireEvent.click(customBtn);

    // Must call onOpenCustomPlot IMMEDIATELY
    expect(onOpenCustomPlot).toHaveBeenCalledTimes(1);
    // Must NOT immediately send "custom irregular plot" as normal user answer
    expect(onAnswer).not.toHaveBeenCalled();
  });

  it('CustomPlotModal renders and allows Cancel without saving', async () => {
    const { CustomPlotModal } = await import('../components/chat/CustomPlotModal');
    const onSave = vi.fn();
    const onCancel = vi.fn();

    const { rerender } = render(
      <CustomPlotModal
        isOpen={true}
        onSave={onSave}
        onCancel={onCancel}
      />
    );

    expect(screen.getByTestId('custom-plot-modal')).toBeDefined();
    expect(screen.getByText(/Custom Plot Dimensions/i)).toBeDefined();
    expect(screen.getAllByText(/Irregular Polygon/i).length).toBeGreaterThan(0);

    const cancelBtn = screen.getByTestId('custom-plot-cancel-btn');
    fireEvent.click(cancelBtn);

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onSave).not.toHaveBeenCalled();

    // Rerender as closed
    rerender(
      <CustomPlotModal
        isOpen={false}
        onSave={onSave}
        onCancel={onCancel}
      />
    );
    expect(screen.queryByTestId('custom-plot-modal')).toBeNull();
  });

  it('CustomPlotModal submits valid irregular boundary on Continue', async () => {
    const { CustomPlotModal } = await import('../components/chat/CustomPlotModal');
    const onSave = vi.fn();
    const onCancel = vi.fn();

    render(
      <CustomPlotModal
        isOpen={true}
        initialPlotData={{
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
        }}
        onSave={onSave}
        onCancel={onCancel}
      />
    );

    const continueBtn = screen.getByTestId('custom-plot-continue-btn');
    fireEvent.click(continueBtn);

    expect(onSave).toHaveBeenCalledTimes(1);
    const savedData = onSave.mock.calls[0][0];
    expect(savedData.mode).toBe('irregular');
    expect(savedData.vertices.length).toBe(5);
    expect(savedData.vertices).toEqual([
      [0, 0],
      [12, 0],
      [12, 8],
      [7, 10],
      [0, 8],
    ]);
  });

  it('CustomPlotModal enforces validation on invalid boundary (< 3 vertices)', async () => {
    const { CustomPlotModal } = await import('../components/chat/CustomPlotModal');
    const onSave = vi.fn();
    const onCancel = vi.fn();

    render(
      <CustomPlotModal
        isOpen={true}
        initialPlotData={{
          mode: 'irregular',
          vertices: [
            [0, 0],
            [10, 0],
          ],
          width: 10,
          length: 10,
          unit: 'm',
          frontSetback: 2,
          rearSetback: 2,
          sideSetback: 2,
          orientation: 'north',
          isClosed: false,
        }}
        onSave={onSave}
        onCancel={onCancel}
      />
    );

    const continueBtn = screen.getByTestId('custom-plot-continue-btn');
    fireEvent.click(continueBtn);

    // Validation must prevent submit!
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByTestId('plot-validation-error')).toBeDefined();
  });

  describe('MessageBubble structured response rendering', () => {
    it('renders response_type "text" purely as message without cards or chips', async () => {
      const { MessageBubble } = await import('../components/chat/MessageBubble');
      const onAnswerCard = vi.fn();

      render(
        <MessageBubble
          message={{
            id: 'm1',
            role: 'assistant',
            text: 'I can help you design single-floor bungalows, duplexes, or custom homes.',
            response_type: 'text',
            intent: 'CAPABILITY_QUERY',
            quick_replies: [],
          }}
          isLatestAssistant={true}
          onAnswerCard={onAnswerCard}
        />
      );

      expect(screen.getByText(/I can help you design single-floor bungalows/i)).toBeDefined();
      expect(screen.queryByTestId('quick-replies')).toBeNull();
      expect(screen.queryByTestId('action-result-card')).toBeNull();
      expect(screen.queryByTestId('confirm-generate-btn')).toBeNull();
    });

    it('renders response_type "quick_replies" and calls onAnswerCard when clicked', async () => {
      const { MessageBubble } = await import('../components/chat/MessageBubble');
      const onAnswerCard = vi.fn();

      render(
        <MessageBubble
          message={{
            id: 'm2',
            role: 'assistant',
            text: 'What type of home are you planning?',
            response_type: 'quick_replies',
            intent: 'PROJECT_TYPE_SELECTION',
            quick_replies: [
              { label: 'Bungalow', value: 'Bungalow' },
              { label: 'Duplex', value: 'Duplex' },
            ],
          }}
          isLatestAssistant={true}
          onAnswerCard={onAnswerCard}
        />
      );

      expect(screen.getByText(/What type of home are you planning\?/i)).toBeDefined();
      const bungalowBtn = screen.getByRole('button', { name: 'Bungalow' });
      const duplexBtn = screen.getByRole('button', { name: 'Duplex' });
      expect(bungalowBtn).toBeDefined();
      expect(duplexBtn).toBeDefined();

      fireEvent.click(duplexBtn);
      expect(onAnswerCard).toHaveBeenCalledWith('Duplex');
    });

    it('renders response_type "action_result" with export payload and triggers download', async () => {
      const { MessageBubble } = await import('../components/chat/MessageBubble');
      const onExecuteAction = vi.fn();

      render(
        <MessageBubble
          message={{
            id: 'm3',
            role: 'assistant',
            text: 'Your DXF export is ready.',
            response_type: 'action_result',
            intent: 'EXPORT_REQUEST',
            action: {
              type: 'export',
              label: 'Export Complete',
              payload: {
                format: 'dxf',
                items: [
                  {
                    format: 'dxf',
                    label: 'CAD Drawing (DXF)',
                    url: 'http://localhost:8000/api/projects/proj-1/export/dxf',
                    available: true,
                    note: 'Ready',
                  },
                ],
              },
            },
          }}
          isLatestAssistant={true}
          onExecuteAction={onExecuteAction}
        />
      );

      expect(screen.getByText(/Your DXF export is ready/i)).toBeDefined();
      expect(screen.getByTestId('export-action-card')).toBeDefined();
      expect(screen.getByText(/1 Available/i)).toBeDefined();
      const downloadBtn = screen.getByTestId('export-btn-dxf');
      expect(downloadBtn).toBeDefined();
      expect(downloadBtn.getAttribute('href')).toBe('http://localhost:8000/api/projects/proj-1/export/dxf');
    });

    it('renders response_type "requirement_summary" with generation trigger button', async () => {
      const { MessageBubble } = await import('../components/chat/MessageBubble');
      const onAnswerCard = vi.fn();

      render(
        <MessageBubble
          message={{
            id: 'm4',
            role: 'assistant',
            text: 'All requirements are captured. Plot: 30x40 ft, Type: Duplex.',
            response_type: 'requirement_summary',
            intent: 'PROJECT_SUMMARY',
            is_ready_for_generation: true,
          }}
          isLatestAssistant={true}
          onAnswerCard={onAnswerCard}
        />
      );

      expect(screen.getByTestId('requirement-summary-card')).toBeDefined();
      const genBtn = screen.getByRole('button', { name: /✓ Generate Floor Plan/i });
      expect(genBtn).toBeDefined();

      fireEvent.click(genBtn);
      expect(onAnswerCard).toHaveBeenCalledWith('Generate Floor Plan');
    });

    it('renders response_type "generation_progress" with live status indicator', async () => {
      const { MessageBubble } = await import('../components/chat/MessageBubble');

      render(
        <MessageBubble
          message={{
            id: 'm5',
            role: 'assistant',
            text: 'Generating your floor plan...',
            response_type: 'generation_progress',
            intent: 'PROJECT_STATUS',
          }}
          isLatestAssistant={true}
        />
      );

      expect(screen.getByTestId('generation-progress-card')).toBeDefined();
      expect(screen.getByText(/Generation In Progress/i)).toBeDefined();
    });
  });
});


