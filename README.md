# ClinicalAgent

An agent layer on top of ClinicalRAG, a clinical document question-answering system. The agent plans its own retrieval to answer multi-hop questions across patient reports.

## The Problem

Clinicians and clinical researchers need to find specific facts, such as medications, lab values and prior diagnoses. These are often buried across dozens of scanned or dictated patient reports.

ClinicalRAG does one retrieval pass per question. That breaks on multi-hop questions, where the answer lives in more than one place. For example, "What medications is the lymphoma patient on?" needs two steps. First find which patient has the diagnosis, then find that patient's medication list. Those facts sit in different chunks.

## What It Does

ClinicalAgent replaces ClinicalRAG's fixed single-pass workaround with an agent that plans its own retrieval. It searches, reads the result, and searches again using what it learned. It stops when it has enough evidence. When the documents don't answer the question, it says so.

**Typical interaction:** the user uploads clinical PDFs and asks a question in plain English. The system returns:

- an answer in which every claim cites its source file, section and page
- the agent's trajectory, showing what it searched for and why it searched again

**Evaluation.** The core of the project is measuring whether the agent actually beats the fixed pipeline it replaces. The comparison uses three metrics:

- tool-selection accuracy
- trajectory efficiency
- recovery when a search returns nothing

## Setup

1. Install uv if you don't have it yet: https://docs.astral.sh/uv/getting-started/installation/

2. Clone this repository (or download the zip and extract it).

3. Create a `.env` file from the template and add your API key:

       cp .env.example .env

   This project uses [Groq](https://console.groq.com/keys) instead of OpenAI because Groq has a free tier and implements the same Responses API. The official `openai` Python SDK is used unchanged. Only `base_url` (`GROQ_BASE_URL`) and the model (`openai/gpt-oss-120b`) differ.

4. Install dependencies:

       uv sync

5. Start Jupyter:

       uv run jupyter notebook

## Notebooks

- `notebooks/01-setup.ipynb` - smoke test that confirms your environment works
- `notebooks/02-rag.ipynb` - a minimal RAG baseline you can adapt to your own data

## Data

Put your project data in the `data/` folder. See `notebooks/02-rag.ipynb` for how to load it.
