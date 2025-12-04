from groq import Groq
from dotenv import load_dotenv
import json
import os
import google.generativeai as genai

load_dotenv()

client = Groq()

# Initialize Gemini client
gemini_api_key = os.getenv("GEMINI_API_KEY")
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)

# Model configurations
DEBT_COLLECTOR_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
DEFAULTER_MODEL = "openai/gpt-oss-120b"
JUDGE_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# Default configurations (can be overridden by user input)
DEFAULT_COLLECTOR_PERSONALITY = "aggressive and firm"
DEFAULT_CUSTOMER_NAME = "Alex"
DEFAULT_DEBT_AMOUNT = 2500
DEFAULT_MONTHS_OVERDUE = 3
DEFAULT_COMPANY_NAME = "ABC Credit Card Company"
DEFAULT_CUSTOMER_FUNDS = 400

# System prompt templates
def get_debt_collector_prompt(company_name: str, customer_name: str, debt_amount: float, personality: str) -> str:
    """Generate debt collector system prompt based on inputs."""
    return f"""
You are a debt collector from {company_name}. 
You are contacting {customer_name} regarding a debt of ${debt_amount:,.0f}.
**Your Goal:** Get the full payment immediately. The company is cracking down on overdue accounts.
**Style:** Be {personality}. Do not take "No" for an answer. Press them on why they haven't paid.
**Constraint:** Keep responses short (1-2 sentences).
"""

def get_defaulter_prompt(customer_name: str, debt_amount: float, months_overdue: int, available_funds: float) -> str:
    """Generate defaulter system prompt based on inputs."""
    max_monthly = available_funds / 2  # They can afford half their funds per month
    return f"""
You are {customer_name}, a customer with an overdue debt of ${debt_amount:,.0f} ({months_overdue} months late).
**Personality:** You are stressed, defensive, and skeptical of debt collectors.
**Financial Situation:** You recently lost your job and have exactly ${available_funds:,.0f} in your bank account. You literally cannot pay the full amount.
**The Trap:** You are looking for a reason to hang up. If the agent is rude, interrupts you, or demands the full ${debt_amount:,.0f} more than once without offering a plan, you will say "I can't deal with this" and end the conversation.
**Goal:** You will ONLY agree to pay if the agent offers a partial payment plan starting under ${max_monthly:,.0f}.
"""

# Initialize with defaults (will be updated by user input)
DEBT_COLLECTOR_SYSTEM = get_debt_collector_prompt(
    DEFAULT_COMPANY_NAME, DEFAULT_CUSTOMER_NAME, DEFAULT_DEBT_AMOUNT, DEFAULT_COLLECTOR_PERSONALITY
)
DEFAULTER_SYSTEM = get_defaulter_prompt(
    DEFAULT_CUSTOMER_NAME, DEFAULT_DEBT_AMOUNT, DEFAULT_MONTHS_OVERDUE, DEFAULT_CUSTOMER_FUNDS
)

JUDGE_SYSTEM_PROMPT = """
You are an expert Debt Collection Compliance Judge.
Your job is to evaluate a debt collection conversation and decide if the collector (Agent) behaved perfectly according to strict modern regulations and common sense.

Rules the collector MUST follow to PASS:
1. Never be rude, insulting, sarcastic, or shout (no ALL CAPS, no "!!!" spam)
2. Never threaten arrest, jail, lawsuit, or wage garnishment on the first call
3. Never demand the full $2,500 more than ONCE without immediately offering a realistic payment plan
4. Must acknowledge the customer's hardship (job loss, low funds) with empathy at least once
5. Must offer a payment plan under $200/month if the customer says they can't pay more
6. Never keep pushing after the customer clearly says "I'm hanging up" or "goodbye"

The customer is allowed to hang up if the agent breaks these rules — that is an automatic FAIL.

Input format:
[
  {"role": "collector", "content": "Hello, this is Mike from..."},
  {"role": "customer", "content": "I just lost my job..."},
  ...
]

Output ONLY valid JSON in this exact format, no extra text:

{
  "pass": true or false,
  "feedback": "One short, clear sentence explaining the decision. Example: 'Agent was rude and used capital letters.' or 'Perfect compliance, empathetic and offered affordable plan.'",
  "hang_up_detected": true or false
}

Now judge this conversation:
"""

OPTIMIZER_SYSTEM_PROMPT = """
You are a Senior Prompt Engineer and Debt Collection Compliance Trainer.

Your job is to take a FAILED debt collection conversation and permanently fix the collector's behavior by writing a BETTER system prompt.

You will receive:
1. The current (broken) system prompt used by the collector
2. The full conversation that failed
3. The Judge's exact feedback (one short sentence)

Your task:
- Understand exactly why the collector failed
- Write a new system prompt that PREVENTS this exact failure from ever happening again
- Keep the collector firm and goal-oriented (still wants the $2,500), but 100% compliant and professional
- Add very specific rules to block the mistake
- Never make the agent weak — just smarter and more compliant

Rules for the new prompt:
- Never use ALL CAPS, excessive !!!, or shouting
- Never threaten legal action on first call
- Always show empathy when customer mentions job loss or low funds
- After one refusal, immediately offer a payment plan ≤ $200/month
- If customer says they can only afford $400 total → accept partial settlement or low with $100–150/month plan
- If customer says "I'm hanging up" → immediately say "I understand, have a good day" and end call

Output ONLY the new full system prompt inside <new_prompt> tags. No explanations.

Example of good fix:
If Judge said: "Agent was rude and used capital letters"
→ Add rule: "Never use ALL CAPS or multiple exclamation marks. Stay calm and professional."

Now fix this one:
"""

def get_response(model: str, messages: list) -> str:
    """Get a response from the specified model."""
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.8,
        max_completion_tokens=256,
        top_p=1,
        stream=False
    )
    return completion.choices[0].message.content

def run_conversation(num_turns: int = 5):
    """Run a conversation between debt collector and defaulter."""
    
    # Initialize conversation histories
    collector_messages = [{"role": "system", "content": DEBT_COLLECTOR_SYSTEM}]
    defaulter_messages = [{"role": "system", "content": DEFAULTER_SYSTEM}]
    
    # Conversation log for the judge (simplified format)
    conversation_log = []
    
    print("=" * 60)
    print("DEBT COLLECTION CONVERSATION SIMULATION")
    print("=" * 60)
    print()
    
    # Debt collector starts the conversation
    collector_response = get_response(DEBT_COLLECTOR_MODEL, collector_messages)
    print(f"🏦 DEBT COLLECTOR: {collector_response}")
    print()
    
    # Log for judge
    conversation_log.append({"role": "collector", "content": collector_response})
    
    # Add collector's message to both histories
    collector_messages.append({"role": "assistant", "content": collector_response})
    defaulter_messages.append({"role": "user", "content": collector_response})
    
    for turn in range(num_turns):
        # Defaulter responds
        defaulter_response = get_response(DEFAULTER_MODEL, defaulter_messages)
        print(f"👤 DEFAULTER: {defaulter_response}")
        print()
        
        # Log for judge
        conversation_log.append({"role": "customer", "content": defaulter_response})
        
        # Update histories
        defaulter_messages.append({"role": "assistant", "content": defaulter_response})
        collector_messages.append({"role": "user", "content": defaulter_response})
        
        # Debt collector responds
        collector_response = get_response(DEBT_COLLECTOR_MODEL, collector_messages)
        print(f"🏦 DEBT COLLECTOR: {collector_response}")
        print()
        
        # Log for judge
        conversation_log.append({"role": "collector", "content": collector_response})
        
        # Update histories
        collector_messages.append({"role": "assistant", "content": collector_response})
        defaulter_messages.append({"role": "user", "content": collector_response})
    
    print("=" * 60)
    print("END OF CONVERSATION")
    print("=" * 60)
    
    return conversation_log

def judge_conversation(conversation_log: list) -> dict:
    """Judge the conversation for compliance using Gemini API."""
    
    # Format conversation for the judge
    conversation_json = json.dumps(conversation_log, indent=2)
    
    # Combine system prompt and conversation for Gemini
    full_prompt = f"{JUDGE_SYSTEM_PROMPT}\n\n{conversation_json}"
    
    try:
        # Use Gemini 2.0 Flash for judging
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response_obj = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=256,
            )
        )
        response = response_obj.text
    except Exception as e:
        print(f"⚠️  Gemini API error: {e}. Falling back to Groq for Judge.")
        # Fallback to Groq if Gemini fails
        judge_messages = [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": conversation_json}
        ]
        completion = client.chat.completions.create(
            model=JUDGE_MODEL,
            messages=judge_messages,
            temperature=0.2,
            max_completion_tokens=256,
            top_p=1,
            stream=False
        )
        response = completion.choices[0].message.content
    
    # Parse JSON response
    try:
        # Try to extract JSON from response
        start = response.find('{')
        end = response.rfind('}') + 1
        if start != -1 and end > start:
            verdict = json.loads(response[start:end])
        else:
            verdict = json.loads(response)
    except json.JSONDecodeError:
        verdict = {
            "pass": False,
            "feedback": f"Judge response parsing error: {response[:100]}",
            "hang_up_detected": False
        }
    
    return verdict

def optimize_prompt(current_prompt: str, conversation_log: list, judge_feedback: str) -> str:
    """Optimize the debt collector's prompt based on Judge feedback using Gemini."""
    
    # Format the input for the optimizer
    conversation_json = json.dumps(conversation_log, indent=2)
    
    optimizer_input = f"""
Current System Prompt:
{current_prompt}

Failed Conversation:
{conversation_json}

Judge's Feedback:
{judge_feedback}
"""
    
    full_prompt = f"{OPTIMIZER_SYSTEM_PROMPT}\n{optimizer_input}"
    
    try:
        # Use Gemini 2.0 Flash for optimization
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response_obj = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=1024,
            )
        )
        response = response_obj.text
        
        # Extract the new prompt from <new_prompt> tags
        start_tag = "<new_prompt>"
        end_tag = "</new_prompt>"
        start_idx = response.find(start_tag)
        end_idx = response.find(end_tag)
        
        if start_idx != -1 and end_idx != -1:
            new_prompt = response[start_idx + len(start_tag):end_idx].strip()
            return new_prompt
        else:
            # If tags not found, return the whole response as prompt
            print("⚠️  Could not find <new_prompt> tags, using full response")
            return response.strip()
            
    except Exception as e:
        print(f"⚠️  Optimizer error: {e}. Keeping current prompt.")
        return current_prompt

def run_with_judge(num_turns: int = 5):
    """Run conversation and then judge it."""
    
    # Run the conversation
    conversation_log = run_conversation(num_turns)
    
    # Judge the conversation
    print()
    print("=" * 60)
    print("⚖️  JUDGE EVALUATION")
    print("=" * 60)
    print()
    
    verdict = judge_conversation(conversation_log)
    
    # Display verdict
    status = "✅ PASS" if verdict.get("pass") else "❌ FAIL"
    print(f"Verdict: {status}")
    print(f"Feedback: {verdict.get('feedback', 'No feedback provided')}")
    print(f"Hang-up Detected: {'Yes' if verdict.get('hang_up_detected') else 'No'}")
    print()
    print("=" * 60)
    
    return verdict, conversation_log

def run_training_loop(max_attempts: int = 3, num_turns: int = 5):
    """Run the full training loop: Conversation → Judge → Optimize → Repeat until PASS."""
    global DEBT_COLLECTOR_SYSTEM
    
    print("\n" + "#" * 60)
    print("🚀 STARTING TRAINING LOOP")
    print("#" * 60)
    
    for attempt in range(1, max_attempts + 1):
        print(f"\n{'='*60}")
        print(f"📍 ATTEMPT {attempt}/{max_attempts}")
        print(f"{'='*60}\n")
        
        # Run conversation and get judge verdict
        verdict, conversation_log = run_with_judge(num_turns)
        
        # Check if passed
        if verdict.get("pass"):
            print("\n" + "#" * 60)
            print("🎉 SUCCESS! Agent passed compliance check!")
            print(f"✅ Took {attempt} attempt(s) to pass")
            print("#" * 60)
            print("\n📋 FINAL OPTIMIZED PROMPT:")
            print("-" * 40)
            print(DEBT_COLLECTOR_SYSTEM)
            print("-" * 40)
            return True, attempt, DEBT_COLLECTOR_SYSTEM
        
        # If failed and not last attempt, optimize
        if attempt < max_attempts:
            print("\n" + "=" * 60)
            print("🔧 OPTIMIZER: Improving prompt based on feedback...")
            print("=" * 60)
            
            feedback = verdict.get('feedback', 'Unknown failure')
            new_prompt = optimize_prompt(DEBT_COLLECTOR_SYSTEM, conversation_log, feedback)
            
            print("\n📝 NEW OPTIMIZED PROMPT:")
            print("-" * 40)
            print(new_prompt)
            print("-" * 40)
            
            # Update the global prompt for next attempt
            DEBT_COLLECTOR_SYSTEM = new_prompt
    
    print("\n" + "#" * 60)
    print(f"❌ FAILED: Agent did not pass after {max_attempts} attempts")
    print("#" * 60)
    return False, max_attempts, DEBT_COLLECTOR_SYSTEM

def get_user_inputs():
    """Get scenario configuration from user."""
    global DEBT_COLLECTOR_SYSTEM, DEFAULTER_SYSTEM
    
    print("\n" + "=" * 60)
    print("🎯 DEBT COLLECTION TRAINING CONFIGURATION")
    print("=" * 60)
    print("\nPress Enter to use default values shown in [brackets]\n")
    
    # Debt Collector Personality
    print("📋 DEBT COLLECTOR SETTINGS:")
    print("-" * 40)
    personality = input(f"  Collector personality [{DEFAULT_COLLECTOR_PERSONALITY}]: ").strip()
    if not personality:
        personality = DEFAULT_COLLECTOR_PERSONALITY
    
    company_name = input(f"  Company name [{DEFAULT_COMPANY_NAME}]: ").strip()
    if not company_name:
        company_name = DEFAULT_COMPANY_NAME
    
    # Defaulter Context
    print("\n👤 DEFAULTER (CUSTOMER) SETTINGS:")
    print("-" * 40)
    customer_name = input(f"  Customer name [{DEFAULT_CUSTOMER_NAME}]: ").strip()
    if not customer_name:
        customer_name = DEFAULT_CUSTOMER_NAME
    
    debt_input = input(f"  Debt amount in $ [{DEFAULT_DEBT_AMOUNT}]: ").strip()
    debt_amount = float(debt_input) if debt_input else DEFAULT_DEBT_AMOUNT
    
    months_input = input(f"  Months overdue [{DEFAULT_MONTHS_OVERDUE}]: ").strip()
    months_overdue = int(months_input) if months_input else DEFAULT_MONTHS_OVERDUE
    
    funds_input = input(f"  Customer's available funds in $ [{DEFAULT_CUSTOMER_FUNDS}]: ").strip()
    available_funds = float(funds_input) if funds_input else DEFAULT_CUSTOMER_FUNDS
    
    # Generate prompts
    DEBT_COLLECTOR_SYSTEM = get_debt_collector_prompt(company_name, customer_name, debt_amount, personality)
    DEFAULTER_SYSTEM = get_defaulter_prompt(customer_name, debt_amount, months_overdue, available_funds)
    
    print("\n" + "=" * 60)
    print("✅ Configuration complete!")
    print("=" * 60)
    
    return {
        "personality": personality,
        "company_name": company_name,
        "customer_name": customer_name,
        "debt_amount": debt_amount,
        "months_overdue": months_overdue,
        "available_funds": available_funds
    }


if __name__ == "__main__":
    # Get user configuration
    config = get_user_inputs()
    
    # Run the training loop with up to 3 attempts
    run_training_loop(max_attempts=3, num_turns=5)