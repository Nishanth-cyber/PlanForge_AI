/**
 * Authoritative Validation Status Helper (Phase 5).
 * Strictly distinguishes:
 * - VALID FLOOR PLAN
 * - VALID — REFINED
 * - PLAN COULD NOT BE VALIDATED
 * - REQUIREMENTS ARE INFEASIBLE
 */

export interface ValidationStatusDisplay {
  label: string;
  type: 'valid' | 'refined' | 'invalid' | 'infeasible';
  badgeClass: string;
}

export function getValidationDisplayStatus(
  validationReport?: { overall_valid?: boolean; total_errors?: number; results?: any[] } | null,
  refinementResult?: { iterations?: any[]; status?: string; total_iterations?: number } | null,
  projectStatus?: string
): ValidationStatusDisplay {
  const normStatus = (projectStatus || '').toLowerCase();
  const refStatus = (refinementResult?.status || '').toLowerCase();

  // 1. Infeasible
  if (
    normStatus === 'failed' ||
    refStatus === 'infeasible' ||
    refStatus === 'infeasible_under_constraints'
  ) {
    return {
      label: 'REQUIREMENTS ARE INFEASIBLE',
      type: 'infeasible',
      badgeClass: 'badge-danger',
    };
  }

  // 2. Error counts and validity
  const errorCount =
    validationReport?.total_errors ??
    validationReport?.results?.reduce(
      (acc: number, r: any) => acc + (r.issues?.filter((i: any) => i.severity === 'error').length || 0),
      0
    ) ??
    0;

  const isValid =
    (validationReport?.overall_valid ?? (errorCount === 0)) &&
    normStatus !== 'unresolved' &&
    normStatus !== 'failed';

  if (!isValid || errorCount > 0) {
    return {
      label: 'PLAN COULD NOT BE VALIDATED',
      type: 'invalid',
      badgeClass: 'badge-danger',
    };
  }

  // 3. Valid with refinement vs Valid initially
  const iterationCount =
    refinementResult?.total_iterations ??
    refinementResult?.iterations?.length ??
    0;

  const hadRefinementPass =
    iterationCount > 0 &&
    refStatus !== 'valid_on_initial_pass' &&
    refStatus !== 'no_refinement_required' &&
    refStatus !== 'no_change';

  if (hadRefinementPass) {
    return {
      label: 'VALID — REFINED',
      type: 'refined',
      badgeClass: 'badge-success',
    };
  }

  return {
    label: 'VALID FLOOR PLAN',
    type: 'valid',
    badgeClass: 'badge-success',
  };
}
