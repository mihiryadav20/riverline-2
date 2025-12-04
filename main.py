from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq()

# Model configurations
DEBT_COLLECTOR_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"
DEFAULTER_MODEL = "openai/gpt-oss-120b"

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
    
    print("=" * 60)
    print("DEBT COLLECTION CONVERSATION SIMULATION")
    print("=" * 60)
    print()
    
    # Debt collector starts the conversation
    collector_response = get_response(DEBT_COLLECTOR_MODEL, collector_messages)
    print(f"🏦 DEBT COLLECTOR: {collector_response}")
    print()
    
    # Add collector's message to both histories
    collector_messages.append({"role": "assistant", "content": collector_response})
    defaulter_messages.append({"role": "user", "content": collector_response})
    
    for turn in range(num_turns):
        # Defaulter responds
        defaulter_response = get_response(DEFAULTER_MODEL, defaulter_messages)
        print(f"👤 DEFAULTER: {defaulter_response}")
        print()
        
        # Update histories
        defaulter_messages.append({"role": "assistant", "content": defaulter_response})
        collector_messages.append({"role": "user", "content": defaulter_response})
        
        # Debt collector responds
        collector_response = get_response(DEBT_COLLECTOR_MODEL, collector_messages)
        print(f"🏦 DEBT COLLECTOR: {collector_response}")
        print()
        
        # Update histories
        collector_messages.append({"role": "assistant", "content": collector_response})
        defaulter_messages.append({"role": "user", "content": collector_response})
    
    print("=" * 60)
    print("END OF CONVERSATION")
    print("=" * 60)

if __name__ == "__main__":
    run_conversation(num_turns=5)