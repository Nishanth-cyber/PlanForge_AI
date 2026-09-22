# PlanForge AI — LLM Runtime & Provider Guide

This document details the configuration, verification, and research integrity protocols for the Large Language Model (LLM) execution paths in PlanForge AI.

---

## 1. Supported Providers

| Provider | Identifier | Default Model | Description & Intended Usage |
| :--- | :--- | :--- | :--- |
| **Deterministic Mock** *(Testing default)* | `mock` | `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` | Offline, deterministic mock generator. Builds valid architectural proposals without external dependencies. Used for unit tests, regression suites, CI/CD, and reproducible benchmarking. |
| **Hugging Face DeepSeek** *(Live LLM)* | `huggingface` (or `hf`) | `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` | Free Serverless Hugging Face Inference API. Executes real neural reasoning and structured architectural design generation (supporting DeepSeek-R1-Distill-Qwen-7B, DeepSeek-V3, and Llama distilled variants) without installing heavy local weights or daemon services. |

---

## 2. Enabling Hugging Face DeepSeek Provider

PlanForge connects to Hugging Face Inference API over standard HTTPS with zero external heavy dependencies (`urllib` based).

### Step 1: Obtain a Free Hugging Face Token (Optional but Recommended)
1. Sign up or log in at [huggingface.co](https://huggingface.co).
2. Go to **Settings -> Access Tokens**.
3. Create a free **Read** access token.

### Step 2: Configure Environment Variables
Set the following variables in your `.env` file:
```env
PLANFORGE_LLM_PROVIDER=huggingface
PLANFORGE_LLM_MODEL=deepseek-ai/DeepSeek-R1-Distill-Qwen-7B
PLANFORGE_HF_BASE_URL=https://api-inference.huggingface.co/models
PLANFORGE_HF_API_KEY=hf_your_free_token_here
PLANFORGE_LLM_TIMEOUT=120.0
```

> [!TIP]
> You can also use the OpenAI-compatible router endpoint by setting:
> ```env
> PLANFORGE_HF_BASE_URL=https://router.huggingface.co/hf-inference/v1/chat/completions
> ```

### Supported DeepSeek Models
- `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` (Recommended: fast, high quality JSON and reasoning)
- `deepseek-ai/DeepSeek-V3`
- `deepseek-ai/DeepSeek-R1-Distill-Llama-8B`

---

## 3. DeepSeek Reasoning & Structured Output Handling

DeepSeek reasoning models generate internal reasoning traces wrapped in `<think>...</think>`.
`HuggingFaceClient` automatically post-processes the output to strip `<think>...</think>` traces and extract the structured architectural proposal JSON payload seamlessly.

---

## 4. Verification and Testing

### A. Runtime Verification Script
Run the dedicated verification script to check endpoint connectivity, model inference, and JSON parsing:
```bash
python scripts/verify_huggingface_runtime.py
```

### B. Representative End-to-End Test
Run a full end-to-end pipeline execution (Requirements -> Planning -> ASAA -> Hugging Face DeepSeek -> Geometry -> Validator):
```bash
python scripts/run_e2e_huggingface_sample.py
```

### C. Automated Pytest Integration Test
Run the integration test (gracefully skips if offline/unreachable):
```bash
python -m pytest tests/integration/test_huggingface_runtime.py -v
```

### D. Unit Tests (Always passing offline via Mock)
Run all LLM provider unit tests:
```bash
python -m pytest tests/unit/test_llm/ -v
```

---

## 5. Architectural Responsibility Division

PlanForge maintains a strict separation of concerns:
- **Requirement Agent**: WHAT — Extracts functional requirements and user dimension constraints.
- **Planning Agent**: ORGANIZE — Groups spaces, assigns zones, priorities, and adjacencies.
- **ASAA Allocator**: WHERE — Authoritative spatial allocation. Rooms must remain within allocated regions.
- **Architectural LLM**: HOW — Proposes room dimensions (when unspecified), semantic shapes, door intents, window intents, and concise rationale.
- **Geometry Engine**: CONSTRUCT — Builds physical walls, exterior boundaries, and room polygons.
- **FloorPlanValidator**: VERIFY — Independent validation verifying non-overlap, egress, setbacks, and dimension constraints.
