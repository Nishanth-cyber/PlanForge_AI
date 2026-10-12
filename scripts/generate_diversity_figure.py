import matplotlib.pyplot as plt
import matplotlib.patches as patches
import shutil

# Set figure size and DPI
fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=200)
fig.patch.set_facecolor('#090d16')
ax.set_facecolor('#090d16')
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis('off')

# Subtle blueprint grid
for x in range(0, 101, 4):
    ax.axvline(x, color='#1e293b', lw=0.5, alpha=0.35, zorder=1)
for y in range(0, 101, 4):
    ax.axhline(y, color='#1e293b', lw=0.5, alpha=0.35, zorder=1)

# Helper function to draw rounded container box
def draw_card(ax, x, y, w, h, bg_color, border_color, title, subtitle=None, zorder=2):
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.5,rounding_size=1.2',
                                  facecolor=bg_color, edgecolor=border_color, linewidth=2, zorder=zorder)
    ax.add_patch(rect)
    ax.text(x + 1.2, y + h - 2.5, title, color='#38bdf8', fontsize=12, fontweight='bold', zorder=zorder+1)
    if subtitle:
        ax.text(x + 1.2, y + h - 4.6, subtitle, color='#94a3b8', fontsize=8.5, style='italic', zorder=zorder+1)

# Header Title
ax.text(3, 95.5, 'PlanForge AI', color='#06b6d4', fontsize=22, fontweight='bold', zorder=5)
ax.text(17.5, 95.5, '|  Multi-Design Generation & Architectural Diversity Filtering', color='#f8fafc', fontsize=18, fontweight='bold', zorder=5)
ax.text(3, 92.5, 'Phase 9 Pipeline: Multi-Strategy Candidate Synthesis, Structural Signatures, and Pairwise Distance Gating', color='#94a3b8', fontsize=10.5, zorder=5)

# --- 1. INPUT CARD ---
draw_card(ax, 3, 56, 17, 32, '#111827', '#0284c7', '1. Input Contracts', 'Strategic & Spatial Basis')
ax.text(4.5, 79.5, '• PlanningSpec', color='#f1f5f9', fontsize=9.5, fontweight='bold', zorder=5)
ax.text(5.5, 73.5, '- Room programs & priorities\n- Adjacency / Separation matrix\n- Entrance & circulation intent\n- Room target & bound areas', color='#cbd5e1', fontsize=8, zorder=5)
ax.text(4.5, 68.5, '• AllocationSet (ASAA)', color='#f1f5f9', fontsize=9.5, fontweight='bold', zorder=5)
ax.text(5.5, 63.5, '- Locked buildable boundary\n- Fixed 2D region envelopes\n- Immutable room assignments\n- Staircase core locked', color='#cbd5e1', fontsize=8, zorder=5)
ax.text(4.5, 59, '• Core Invariant:', color='#fbbf24', fontsize=8.5, fontweight='bold', zorder=5)
ax.text(5.5, 57, '100% room preservation (no hallu)', color='#94a3b8', fontsize=7.5, zorder=5)

# --- 2. STRATEGY SYNTHESIS CARD ---
draw_card(ax, 23, 56, 23, 32, '#111827', '#6366f1', '2. Strategy Synthesis', '6 Distinct Architectural Archetypes')
strategies = [
    ('1. Social-Centric', 'Direct living-dining-kitchen flow; entertaining', '#38bdf8'),
    ('2. Corridor-Centric', 'Hierarchical central spine; acoustic bedroom buffer', '#818cf8'),
    ('3. Compact Circulation', 'Direct room transitions; minimal hallway footprint', '#a78bfa'),
    ('4. Privacy-Centric', 'Deep separation between public & private wings', '#c084fc'),
    ('5. Open Social', 'Expansive vistas; unified open-concept living', '#f472b6'),
    ('6. Service Clustered', 'Consolidated kitchen, plumbing & utility core', '#fb7185'),
]
sy = 79.5
for name, desc, col in strategies:
    ax.text(24.5, sy, name, color=col, fontsize=8.5, fontweight='bold', zorder=5)
    ax.text(24.5, sy - 1.8, desc, color='#94a3b8', fontsize=7.2, zorder=5)
    sy -= 4.3

# --- 3. SYNTHESIS & VALIDATION CARD ---
draw_card(ax, 49, 56, 23, 32, '#111827', '#8b5cf6', '3. Generation & Verification', 'Intent -> Geometry -> Validation')
def draw_subbox(ax, x, y, w, h, title, sub, border_col, bg_col):
    box = patches.FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.3,rounding_size=0.6', facecolor=bg_col, edgecolor=border_col, linewidth=1.2, zorder=3)
    ax.add_patch(box)
    ax.text(x+0.8, y+h-1.6, title, color='#f8fafc', fontsize=8.5, fontweight='bold', zorder=4)
    ax.text(x+0.8, y+0.8, sub, color='#94a3b8', fontsize=7.2, zorder=4)

draw_subbox(ax, 50.5, 77.5, 20, 4.5, 'LLM Architectural Designer', 'Proposes RoomDesign, DoorIntent, Windows', '#8b5cf6', '#1e1b4b')
draw_subbox(ax, 50.5, 71.0, 20, 4.5, 'Geometry Engine (Shapely CAD)', 'Constructs GeoWalls, GeoDoors, GeoStairs', '#06b6d4', '#083344')
draw_subbox(ax, 50.5, 64.5, 20, 4.5, 'Independent Validator (18 Checks)', 'Zero self-certification; strict code audit', '#10b981', '#064e3b')
draw_subbox(ax, 50.5, 58.0, 20, 4.5, 'Refinement Loop (Closed Feedback)', 'Iterative correction with oscillation guard', '#f59e0b', '#451a03')

# --- 4. SIGNATURE EXTRACTOR CARD ---
draw_card(ax, 75, 56, 22, 32, '#111827', '#ec4899', '4. Structural Signature', 'DesignSignature Vector')
ax.text(76.5, 79.5, 'Topological & Geometric Features:', color='#f1f5f9', fontsize=8.5, fontweight='bold', zorder=5)

features = [
    ('Adjacency Graph (E)', 'w = 0.40', 'Door-connected pairs Jaccard dist'),
    ('Circulation Topology', 'w = 0.20', 'Open vs spine vs compact hub'),
    ('Entrance Room', 'w = 0.10', 'Primary welcoming threshold'),
    ('Social Sequence', 'w = 0.10', 'Public space traversal order'),
    ('Private Clustering', 'w = 0.05', 'Wing acoustic sequestering'),
    ('Core Access', 'w = 0.05', 'Vertical circulation relation'),
    ('Room Shapes & Ratios', 'w = 0.10', 'Semantic shapes & aspect ratios'),
]
fy = 76.5
for fn, wt, fd in features:
    ax.text(76.5, fy, f'• {fn}', color='#f8fafc', fontsize=7.8, fontweight='bold', zorder=5)
    ax.text(89.5, fy, wt, color='#38bdf8', fontsize=7.8, fontweight='bold', zorder=5)
    ax.text(78, fy - 1.4, fd, color='#94a3b8', fontsize=6.8, zorder=5)
    fy -= 2.9

# --- 5. PAIRWISE DIVERSITY EVALUATOR & FILTERING GATE ---
draw_card(ax, 3, 6, 56, 45, '#111827', '#f59e0b', '5. Pairwise Diversity Evaluator & Gatekeeper', 'Metric Calculation & Filtering Thresholds')

# Formula Box
fbox = patches.FancyBboxPatch((4.5, 33), 53, 11.5, boxstyle='round,pad=0.5,rounding_size=0.8', facecolor='#1e293b', edgecolor='#64748b', linewidth=1.2, zorder=3)
ax.add_patch(fbox)
ax.text(6, 41.5, 'Normalized Multi-Attribute Pairwise Distance Metric:', color='#38bdf8', fontsize=9.5, fontweight='bold', zorder=4)
ax.text(6, 38.5, r'$D(A, B) = \sum_{k} w_k \cdot \delta_k(A, B) \quad \in [0.0, 1.0]$', color='#f8fafc', fontsize=11.5, fontweight='bold', zorder=4)
ax.text(6, 35.0, 'Properties:   Identity: D(A, A) = 0.0   |   Symmetry: D(A, B) = D(B, A)   |   Normalized: 0.0 <= D <= 1.0', color='#94a3b8', fontsize=8, zorder=4)

# Decision Branches inside Gate
# Reject 1: Duplicate
rbox1 = patches.FancyBboxPatch((5, 20.5), 24, 10.5, boxstyle='round,pad=0.4,rounding_size=0.8', facecolor='#450a0a', edgecolor='#ef4444', linewidth=1.5, zorder=3)
ax.add_patch(rbox1)
ax.text(6.5, 28.5, 'REJECT: Exact Duplicate', color='#ef4444', fontsize=10, fontweight='bold', zorder=4)
ax.text(6.5, 26.0, 'Condition: D(A, B) == 0.0', color='#fca5a5', fontsize=8.5, fontweight='bold', zorder=4)
ax.text(6.5, 23.0, 'Identical door graph & circulation\nRejectionReason.DUPLICATE', color='#f87171', fontsize=7.5, zorder=4)

# Reject 2: Near Duplicate
rbox2 = patches.FancyBboxPatch((31, 20.5), 26.5, 10.5, boxstyle='round,pad=0.4,rounding_size=0.8', facecolor='#451a03', edgecolor='#f97316', linewidth=1.5, zorder=3)
ax.add_patch(rbox2)
ax.text(32.5, 28.5, 'REJECT: Insufficient Diversity', color='#f97316', fontsize=10, fontweight='bold', zorder=4)
ax.text(32.5, 26.0, r'Condition: $D(A, B) < 0.15$ (Default $\tau_{div}$)', color='#fdba74', fontsize=8.5, fontweight='bold', zorder=4)
ax.text(32.5, 23.0, 'Minor coordinate jitter or trivial shift\nRejectionReason.INSUFFICIENT_DIVERSITY', color='#fb923c', fontsize=7.5, zorder=4)

# Pass: Accepted Diverse
abox = patches.FancyBboxPatch((5, 8.5), 52.5, 10, boxstyle='round,pad=0.4,rounding_size=0.8', facecolor='#064e3b', edgecolor='#10b981', linewidth=1.8, zorder=3)
ax.add_patch(abox)
ax.text(6.5, 15.5, r'ACCEPT: Valid & Structurally Diverse ($D(A, B) \geq 0.15$)', color='#10b981', fontsize=10.5, fontweight='bold', zorder=4)
ax.text(6.5, 13.0, 'Verified 100% compliant by Validator + genuinely distinct spatial experience', color='#6ee7b7', fontsize=8.5, zorder=4)
ax.text(6.5, 10.5, 'Retains all required rooms, areas, and multi-floor core alignment', color='#a7f3d0', fontsize=8, zorder=4)

# --- 6. OUTPUT CARD ---
draw_card(ax, 62, 6, 35, 45, '#111827', '#10b981', '6. Final Deliverable: DesignAlternativeSet', 'Audited, Publication-Ready Floor Plans')

def draw_alt(ax, x, y, title, strat, div_score, val_score):
    box = patches.FancyBboxPatch((x, y), 31, 6.8, boxstyle='round,pad=0.3,rounding_size=0.6', facecolor='#1e293b', edgecolor='#3b82f6', linewidth=1.2, zorder=4)
    ax.add_patch(box)
    ax.text(x+1, y+4.5, title, color='#f8fafc', fontsize=8.5, fontweight='bold', zorder=5)
    ax.text(x+1, y+2.7, f'Strategy: {strat}', color='#94a3b8', fontsize=7.5, zorder=5)
    ax.text(x+1, y+1.1, f'Div Dist: {div_score} | Validation Score: {val_score}', color='#10b981', fontsize=7.2, fontweight='bold', zorder=5)

draw_alt(ax, 64, 38.5, 'Alternative 1 (Primary Baseline)', 'Social-Centric Flow', 'Reference (0.00)', '96.5 / 100')
draw_alt(ax, 64, 30.0, 'Alternative 2 (Acoustic Buffer)', 'Corridor-Centric Hierarchy', 'D(1,2) = 0.42 >= 0.15', '94.0 / 100')
draw_alt(ax, 64, 21.5, 'Alternative 3 (Modern Open Plan)', 'Open Social Vista', 'D(1,3) = 0.38, D(2,3) = 0.29', '95.2 / 100')

# Matrix box
mbox = patches.FancyBboxPatch((64, 8.5), 31, 11, boxstyle='round,pad=0.3,rounding_size=0.6', facecolor='#0f172a', edgecolor='#64748b', linewidth=1, zorder=4)
ax.add_patch(mbox)
ax.text(65.5, 17.0, 'Pairwise Diversity Matrix [D_ij]:', color='#38bdf8', fontsize=8, fontweight='bold', zorder=5)
ax.text(65.5, 14.8, '            Alt 1     Alt 2     Alt 3', color='#cbd5e1', fontfamily='monospace', fontsize=7.5, zorder=5)
ax.text(65.5, 13.0, 'Alt 1   [  0.00      0.42      0.38  ]', color='#cbd5e1', fontfamily='monospace', fontsize=7.5, zorder=5)
ax.text(65.5, 11.2, 'Alt 2   [  0.42      0.00      0.29  ]', color='#cbd5e1', fontfamily='monospace', fontsize=7.5, zorder=5)
ax.text(65.5, 9.4,  'Alt 3   [  0.38      0.29      0.00  ]', color='#cbd5e1', fontfamily='monospace', fontsize=7.5, zorder=5)

# --- CONNECTOR ARROWS ---
def draw_arrow(ax, x1, y1, x2, y2, color='#38bdf8', lw=2):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=lw, shrinkA=3, shrinkB=3), zorder=6)

# Flow 1 -> 2
draw_arrow(ax, 20, 72, 23, 72)
# Flow 2 -> 3
draw_arrow(ax, 46, 72, 49, 72)
# Flow 3 -> 4
draw_arrow(ax, 72, 72, 75, 72)

# Flow 4 -> 5 (curved connector)
ax.annotate('', xy=(31, 51), xytext=(86, 56),
            arrowprops=dict(arrowstyle='->', color='#ec4899', lw=2.2, connectionstyle='arc3,rad=-0.2'), zorder=6)

# Flow 5 -> 6
draw_arrow(ax, 59, 28, 62, 28, color='#10b981', lw=2.5)

plt.subplots_adjust(left=0.01, right=0.99, top=0.98, bottom=0.02)
plt.savefig('docs/multi_design_diversity.png', facecolor=fig.get_facecolor(), edgecolor='none', dpi=200)
shutil.copyfile('docs/multi_design_diversity.png', r'C:\Users\user\.gemini\antigravity-ide\brain\afbe7109-7049-4a6b-8b2c-b1b56743ee6d\multi_design_diversity.png')
print('Successfully generated docs/multi_design_diversity.png and copied to artifacts')
