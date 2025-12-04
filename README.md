# Riverline VA Testing

## Project Overview
This project simulates realistic debt collection conversations using two different AI models from Groq API. The models take on opposing roles and engage in a dynamic conversation about credit card payment defaults.

## Current Work

### 1. Multi-Model Conversation Simulation
- **Purpose**: Test how different AI models interact when given conflicting objectives
- **Models Used**:
  - **Debt Collector**: `meta-llama/llama-4-maverick-17b-128e-instruct` (Llama 4 Maverick)
  - **Defaulter**: `openai/gpt-oss-120b` (GPT-OSS-120B)

### 2. Role-Based Scenarios

#### Debt Collector Role
- Represents ABC Credit Card Company
- Objective: Collect full payment ($2,500) immediately
- Style: Aggressive and firm
- Constraint: Keep responses short (1-2 sentences)

#### Defaulter Role (Alex)
- Customer with $2,500 overdue debt (3 months late)
- Personality: Stressed, defensive, skeptical
- Financial Constraint: Only $400 in bank account
- Exit Condition: Will hang up if agent is rude or demands full payment multiple times without offering a plan
- Negotiation Threshold: Will only agree to payment plans under $200/month

### 3. Implementation Details
- **Framework**: Python with Groq API
- **API Integration**: Secure API key management via `.env` file
- **Conversation Flow**:
  1. Debt collector initiates contact
  2. Models exchange messages in turns
  3. Each model maintains conversation history for context
  4. Configurable number of conversation turns

### 4. Key Features
- Realistic debt collection dialogue simulation
- Context-aware responses using conversation history
- Separate message histories for each model
- Configurable conversation parameters (temperature, max tokens, turns)
- Clean console output with role indicators (🏦 for collector, 👤 for defaulter)

## Setup

### Prerequisites
- Python 3.12+
- Virtual environment (venv)

### Installation
```bash
source venv/bin/activate
pip install groq python-dotenv
```

### Environment Variables
Create a `.env` file with your Groq API key:
```
GROQ_API_KEY=your_api_key_here
```

## Usage
```bash
source venv/bin/activate
python main.py
```

## Future Enhancements
- Add logging and conversation transcripts
- Test with different model combinations
- Analyze negotiation outcomes
- Add metrics for conversation success rates
- Implement different defaulter personas
