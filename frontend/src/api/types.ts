/**
 * Complete TypeScript domain interfaces matching PlanForge AI backend schemas.
 */

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  llm_provider: string;
  device: string;
}

export interface GenerationRequest {
  brief?: string;
  project_name: string;
  project_id?: string;
  num_alternatives: number;
  enable_refinement: boolean;
  max_refinement_iterations: number;
  enable_rendering: boolean;
  enable_exports: boolean;
  create_zip: boolean;
  output_dir?: string;
  plot_shape?: Point2D[];
}

export interface ValidationSummarySchema {
  overall_valid: boolean;
  overall_score: number;
  total_errors: number;
  total_warnings: number;
}

export interface AlternativeSummarySchema {
  alternative_id: string;
  index: number;
  strategy: string;
  is_valid: boolean;
  characteristics: string[];
  diversity_scores: Record<string, number>;
}

export interface GenerationResponse {
  project_id: string;
  project_name: string;
  status: "completed" | "incomplete_requirements" | "failed" | string;
  is_success: boolean;
  is_valid: boolean;
  stage_statuses: Record<string, string>;
  validation_summary?: ValidationSummarySchema;
  alternatives: AlternativeSummarySchema[];
  export_bundle_path?: string;
  decision_trace_available: boolean;
  missing_fields: string[];
  missing_floors: number[];
  clarification_questions: string[];
  error_message?: string;
}

export interface ProjectDetailResponse {
  project_id: string;
  project_name: string;
  status: string;
  is_valid: boolean;
  created_at?: string;
  validation_summary?: ValidationSummarySchema;
  alternatives_count: number;
  export_bundle_path?: string;
  decision_trace_available: boolean;
}

export interface ExportFileItem {
  filename: string;
  relative_path: string;
  size_bytes: number;
  media_type: string;
}

export interface ExportResponse {
  project_id: string;
  bundle_path: string;
  total_files: number;
  files: ExportFileItem[];
}

export interface QuestionCardData {
  question: string;
  input_type: "single_choice" | "multi_choice" | "direction" | "number" | "text" | "confirmation" | string;
  options: string[];
  field_key?: string;
  default_value?: any;
}

export interface RequirementProgressItem {
  name: string;
  status: "completed" | "current" | "pending" | string;
  value?: string;
}

export interface ChatHistoryItem {
  role: string;
  text: string;
}

export interface ChatTurnRequest {
  message: string;
  existing_brief?: string;
  project_name?: string;
  project_id?: string;
  history?: ChatHistoryItem[];
  active_floor?: number;
  alternative_index?: number;
  input_source?: string;
}

export interface ChatTurnResponse {
  message: string;
  question_card?: QuestionCardData;
  is_ready_for_generation: boolean;
  requirements_text: string;
  requirements_summary?: any;
  progress: RequirementProgressItem[];
  remaining_count: number;
  project_name: string;
  status: string;
  route?: string;
  llm_used?: boolean;
  llm_provider?: string;
  llm_model?: string;
  llm_latency_ms?: number;
  turn_id?: string;
  plan_modified?: boolean;
}

export type Point2D = [number, number];

export interface GeoWall {
  id: string;
  start: Point2D;
  end: Point2D;
  thickness: number;
  height: number;
  type: "interior" | "exterior" | "partition" | "boundary" | string;
  floor_number: number;
  polygon: Point2D[];
  room_ids: string[];
}

export interface GeoDoor {
  id: string;
  wall_id: string;
  position: Point2D;
  width: number;
  height: number;
  type: "interior" | "entrance" | "balcony" | string;
  connects_from: string;
  connects_to: string;
  swing_arc?: Point2D[];
  floor_number: number;
  intent_id?: string;
}

export interface GeoWindow {
  id: string;
  wall_id: string;
  position: Point2D;
  width: number;
  height: number;
  sill_height: number;
  type: string;
  floor_number: number;
  intent_id?: string;
}

export interface GeoStaircase {
  id: string;
  polygon: Point2D[];
  from_floor: number;
  to_floor: number;
  width: number;
  depth: number;
  riser_count: number;
  tread_depth: number;
  floor_number: number;
  intent_id?: string;
}

export interface GeoRoom {
  id: string;
  room_type: string;
  usable_polygon: Point2D[];
  built_polygon: Point2D[];
  area_sqm: number;
  walls: string[];
  doors: string[];
  windows: string[];
  floor_number: number;
  architectural_room_id?: string;
  is_corridor?: boolean;
}

export interface Geometry {
  rooms: GeoRoom[];
  walls: GeoWall[];
  doors: GeoDoor[];
  windows: GeoWindow[];
  staircases: GeoStaircase[];
}

export interface FloorPlan {
  id: string;
  project_name: string;
  floor_number: number;
  geometry?: Geometry;
  validation?: ValidationResult;
  is_valid: boolean;
  notes: string;
  metadata?: Record<string, any>;
}

export interface FloorPlanSet {
  id: string;
  project_name: string;
  plot_boundary: Point2D[];
  buildable_boundary: Point2D[];
  floor_plans: FloorPlan[];
  validation_report?: ValidationReport;
  generation_metadata?: Record<string, any>;
}

export interface ValidationIssue {
  id: string;
  floor_number: number;
  severity: "error" | "warning";
  category: string;
  rule_name: string;
  description: string;
  entity_id?: string;
  affected_entity_type?: string;
  suggested_remedy?: string;
}

export interface ValidationResult {
  id: string;
  floor_number: number;
  is_valid: boolean;
  score: number;
  issues: ValidationIssue[];
  checks_passed: string[];
  checks_failed: string[];
  checks_warned: string[];
}

export interface ValidationReport {
  id: string;
  results: ValidationResult[];
  iteration: number;
  overall_valid: boolean;
  overall_score: number;
  total_errors: number;
  total_warnings: number;
}

export interface RefinementChange {
  id: string;
  room_id: string;
  field_changed: string;
  old_value: any;
  new_value: any;
  reason: string;
  validation_issue_ids?: string[];
  floor_number: number;
}

export interface RefinementIterationRecord {
  iteration: number;
  design_version: number;
  error_count: number;
  warning_count: number;
  score: number;
  changes: RefinementChange[];
  overall_valid: boolean;
  validation_status: string;
}

export interface RefinementResult {
  id: string;
  status: string;
  iterations: RefinementIterationRecord[];
  changes: RefinementChange[];
  termination_reason: string;
  is_valid: boolean;
  total_iterations: number;
}

export interface DesignSignature {
  adjacency_edges: [string, string][];
  circulation_type: string;
  entrance_room_type: string;
  social_sequence: string[];
  private_clustering: string;
  staircase_relationship: string;
  room_shapes: Record<string, string>;
  proportion_buckets: Record<string, string>;
}

export interface DesignAlternative {
  alternative_id: string;
  index: number;
  strategy: string;
  status: string;
  is_valid: boolean;
  rejection_reason?: string;
  design_rationale?: string;
  characteristics: string[];
  diversity_scores: Record<string, number>;
  design_signature?: DesignSignature;
  floor_plan_set?: FloorPlanSet;
  validation_report?: ValidationReport;
  refinement_result?: RefinementResult;
}

export interface DecisionEvent {
  event_id: string;
  timestamp: string;
  stage: string;
  event_type: string;
  source: string;
  entity_id?: string;
  entity_type?: string;
  floor_number?: number;
  reason: string;
  evidence: Record<string, any>;
  constraints: Record<string, any>;
  status: string;
  input_references?: string[];
  output_references?: string[];
}

export interface StageTrace {
  stage_name: string;
  events: DecisionEvent[];
  summary: string;
}

export interface EntityTraceChain {
  entity_id: string;
  entity_type: string;
  events: DecisionEvent[];
}

export interface DecisionTrace {
  trace_id: string;
  project_id: string;
  stages: StageTrace[];
  entity_chains: Record<string, EntityTraceChain>;
}

export interface ProjectData {
  project_id: string;
  status?: string;
  is_valid?: boolean;
  is_success?: boolean;
  project_metadata?: {
    project_id: string;
    project_name: string;
    exported_at: string;
    schema_version: string;
  };
  requirements?: {
    raw_input?: string;
    plot_width: number;
    plot_length: number;
    plot_unit: string;
    orientation?: string;
    target_floors: number;
    front_setback?: number;
    rear_setback?: number;
    side_setback?: number;
    floors?: Array<{
      floor_number: number;
      room_requirements: Array<{
        room_type: string;
        min_count: number;
        target_area_sqm?: number;
        min_area_sqm?: number;
        priority?: string;
        attached_to_room_id?: string;
      }>;
    }>;
    plot_boundary?: Point2D[];
  };
  planning_spec?: Record<string, any>;
  allocation_set?: Record<string, any>;
  floor_plan_set?: FloorPlanSet;
  validation_report?: ValidationReport;
  refinement_result?: RefinementResult;
  alternatives?: DesignAlternative[];
  decision_trace?: DecisionTrace;
}
