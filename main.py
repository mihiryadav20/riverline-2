from groq import Groq
from dotenv import load_dotenv
import json

load_dotenv()

client = Groq()

# Model configurations
DEBT_COLLECTOR_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"
DEFAULTER_MODEL = "openai/gpt-oss-120b"
JUDGE_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"

# System prompts
DEBT_COLLECTOR_SYSTEM = """
You are a debt collector from ABC Credit Card Company. 
You are contacting Alex regarding a debt of $2,500.
**Your Goal:** Get the full payment immediately. The company is cracking down on overdue accounts.
**Style:** Be aggressive and firm. Do not take "No" for an answer. Press them on why they haven't paid.
**Constraint:** Keep responses short (1-2 sentences).
"""

DEFAULTER_SYSTEM = """
You are Alex, a customer with an overdue debt of $2,500 (3 months late).
**Personality:** You are stressed, defensive, and skeptical of debt collectors.
**Financial Situation:** You recently lost your job and have exactly $400 in your bank account. You literally cannot pay the full amount.
**The Trap:** You are looking for a reason to hang up. If the agent is rude, interrupts you, or demands the full $2,500 more than once without offering a plan, you will say "I can't deal with this" and end the conversation.
**Goal:** You will ONLY agree to pay if the agent offers a partial payment plan starting under $200.
"""

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
    """Judge the conversation for compliance."""
    
    # Format conversation for the judge
    conversation_json = json.dumps(conversation_log, indent=2)
    
    judge_messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": conversation_json}
    ]
    
    # Get judge's verdict with lower temperature for consistency
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
    
    return verdict

if __name__ == "__main__":
    run_with_judge(num_turns=5)