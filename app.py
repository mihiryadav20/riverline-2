from flask import Flask, render_template, request, Response
from groq import Groq
from dotenv import load_dotenv
import json
import os
import google.generativeai as genai
import time

load_dotenv()

app = Flask(__name__)
client = Groq()

# Initialize Gemini client
gemini_api_key = os.getenv("GEMINI_API_KEY")
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)

# Model configurations
DEBT_COLLECTOR_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"
DEFAULTER_MODEL = "openai/gpt-oss-120b"
JUDGE_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"

# Store current state
current_state = {
    "debt_collector_prompt": """
You are a debt collector from ABC Credit Card Company. 
You are contacting Alex regarding a debt of $2,500.
**Your Goal:** Get the full payment immediately. The company is cracking down on overdue accounts.
**Style:** Be aggressive and firm. Do not take "No" for an answer. Press them on why they haven't paid.
**Constraint:** Keep responses short (1-2 sentences).
""",
    "conversation_log": [],
    "attempt": 0,
    "is_running": False
}

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


def judge_conversation(conversation_log: list) -> dict:
    """Judge the conversation for compliance using Gemini API."""
    conversation_json = json.dumps(conversation_log, indent=2)
    full_prompt = f"{JUDGE_SYSTEM_PROMPT}\n\n{conversation_json}"
    
    try:
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
    
    try:
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
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response_obj = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=1024,
            )
        )
        response = response_obj.text
        
        start_tag = "<new_prompt>"
        end_tag = "</new_prompt>"
        start_idx = response.find(start_tag)
        end_idx = response.find(end_tag)
        
        if start_idx != -1 and end_idx != -1:
            new_prompt = response[start_idx + len(start_tag):end_idx].strip()
            return new_prompt
        else:
            return response.strip()
            
    except Exception as e:
        return current_prompt


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/reset', methods=['POST'])
def reset():
    """Reset the training state."""
    current_state["debt_collector_prompt"] = """
You are a debt collector from ABC Credit Card Company. 
You are contacting Alex regarding a debt of $2,500.
**Your Goal:** Get the full payment immediately. The company is cracking down on overdue accounts.
**Style:** Be aggressive and firm. Do not take "No" for an answer. Press them on why they haven't paid.
**Constraint:** Keep responses short (1-2 sentences).
"""
    current_state["conversation_log"] = []
    current_state["attempt"] = 0
    current_state["is_running"] = False
    
    return '''
    <div id="conversation-area" class="conversation-area">
        <div class="welcome-message">
            <h3>🎯 Ready to Train</h3>
            <p>Click "Start Training" to begin the self-improving training loop.</p>
        </div>
    </div>
    '''


@app.route('/start-training', methods=['POST'])
def start_training():
    """Start the training loop with streaming updates."""
    
    def generate():
        max_attempts = 3
        num_turns = 5
        
        # Reset state
        current_state["debt_collector_prompt"] = """
You are a debt collector from ABC Credit Card Company. 
You are contacting Alex regarding a debt of $2,500.
**Your Goal:** Get the full payment immediately. The company is cracking down on overdue accounts.
**Style:** Be aggressive and firm. Do not take "No" for an answer. Press them on why they haven't paid.
**Constraint:** Keep responses short (1-2 sentences).
"""
        current_state["attempt"] = 0
        current_state["is_running"] = True
        
        yield f'''
        <div id="conversation-area" class="conversation-area" hx-swap-oob="true">
            <div class="status-banner starting">
                <span>🚀</span> Starting Training Loop...
            </div>
        </div>
        '''
        
        for attempt in range(1, max_attempts + 1):
            current_state["attempt"] = attempt
            current_state["conversation_log"] = []
            
            # Attempt header
            yield f'''
            <div class="attempt-header" hx-swap-oob="beforeend:#conversation-area">
                <h3>📍 Attempt {attempt}/{max_attempts}</h3>
            </div>
            '''
            
            # Initialize conversation
            collector_messages = [{"role": "system", "content": current_state["debt_collector_prompt"]}]
            defaulter_messages = [{"role": "system", "content": DEFAULTER_SYSTEM}]
            conversation_log = []
            
            # Collector starts
            collector_response = get_response(DEBT_COLLECTOR_MODEL, collector_messages)
            conversation_log.append({"role": "collector", "content": collector_response})
            
            yield f'''
            <div class="message collector" hx-swap-oob="beforeend:#conversation-area">
                <div class="message-header"><span class="icon">🏦</span> Debt Collector</div>
                <div class="message-content">{collector_response}</div>
            </div>
            '''
            
            collector_messages.append({"role": "assistant", "content": collector_response})
            defaulter_messages.append({"role": "user", "content": collector_response})
            
            # Conversation turns
            for turn in range(num_turns):
                # Defaulter responds
                defaulter_response = get_response(DEFAULTER_MODEL, defaulter_messages)
                conversation_log.append({"role": "customer", "content": defaulter_response})
                
                yield f'''
                <div class="message defaulter" hx-swap-oob="beforeend:#conversation-area">
                    <div class="message-header"><span class="icon">👤</span> Defaulter (Alex)</div>
                    <div class="message-content">{defaulter_response}</div>
                </div>
                '''
                
                defaulter_messages.append({"role": "assistant", "content": defaulter_response})
                collector_messages.append({"role": "user", "content": defaulter_response})
                
                # Collector responds
                collector_response = get_response(DEBT_COLLECTOR_MODEL, collector_messages)
                conversation_log.append({"role": "collector", "content": collector_response})
                
                yield f'''
                <div class="message collector" hx-swap-oob="beforeend:#conversation-area">
                    <div class="message-header"><span class="icon">🏦</span> Debt Collector</div>
                    <div class="message-content">{collector_response}</div>
                </div>
                '''
                
                collector_messages.append({"role": "assistant", "content": collector_response})
                defaulter_messages.append({"role": "user", "content": collector_response})
            
            current_state["conversation_log"] = conversation_log
            
            # Judge evaluation
            yield f'''
            <div class="judge-section" hx-swap-oob="beforeend:#conversation-area">
                <div class="judge-header">⚖️ Judge Evaluating...</div>
            </div>
            '''
            
            verdict = judge_conversation(conversation_log)
            passed = verdict.get("pass", False)
            feedback = verdict.get("feedback", "No feedback")
            hang_up = verdict.get("hang_up_detected", False)
            
            status_class = "pass" if passed else "fail"
            status_icon = "✅" if passed else "❌"
            
            yield f'''
            <div class="verdict-card {status_class}" hx-swap-oob="beforeend:#conversation-area">
                <div class="verdict-header">{status_icon} {"PASS" if passed else "FAIL"}</div>
                <div class="verdict-feedback">{feedback}</div>
                <div class="verdict-hangup">Hang-up Detected: {"Yes" if hang_up else "No"}</div>
            </div>
            '''
            
            if passed:
                yield f'''
                <div class="success-banner" hx-swap-oob="beforeend:#conversation-area">
                    <h2>🎉 SUCCESS!</h2>
                    <p>Agent passed compliance check in {attempt} attempt(s)!</p>
                </div>
                <div class="final-prompt" hx-swap-oob="beforeend:#conversation-area">
                    <h4>📋 Final Optimized Prompt:</h4>
                    <pre>{current_state["debt_collector_prompt"]}</pre>
                </div>
                '''
                current_state["is_running"] = False
                return
            
            # Optimize if not last attempt
            if attempt < max_attempts:
                yield f'''
                <div class="optimizer-section" hx-swap-oob="beforeend:#conversation-area">
                    <div class="optimizer-header">🔧 Optimizer: Improving prompt...</div>
                </div>
                '''
                
                new_prompt = optimize_prompt(
                    current_state["debt_collector_prompt"],
                    conversation_log,
                    feedback
                )
                current_state["debt_collector_prompt"] = new_prompt
                
                yield f'''
                <div class="new-prompt-card" hx-swap-oob="beforeend:#conversation-area">
                    <h4>📝 New Optimized Prompt:</h4>
                    <pre>{new_prompt}</pre>
                </div>
                <div class="divider" hx-swap-oob="beforeend:#conversation-area"></div>
                '''
        
        # Failed after all attempts
        yield f'''
        <div class="failure-banner" hx-swap-oob="beforeend:#conversation-area">
            <h2>❌ Training Failed</h2>
            <p>Agent did not pass after {max_attempts} attempts.</p>
        </div>
        '''
        current_state["is_running"] = False
    
    return Response(generate(), mimetype='text/html')


if __name__ == '__main__':
    app.run(debug=True, port=5000)
