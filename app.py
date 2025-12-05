from flask import Flask, render_template, request, Response, send_file, jsonify
from groq import Groq
from dotenv import load_dotenv
import json
import os
import google.generativeai as genai
import time
import uuid
import io
from elevenlabs import ElevenLabs

load_dotenv()

app = Flask(__name__)
client = Groq()

# Initialize Gemini client
gemini_api_key = os.getenv("GEMINI_API_KEY")
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)

# Initialize ElevenLabs client
elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
elevenlabs_client = None
TTS_ENABLED = True  # Set to True when you have ElevenLabs credits available
if elevenlabs_api_key and TTS_ENABLED:
    elevenlabs_client = ElevenLabs(api_key=elevenlabs_api_key)

# Voice IDs for different speakers (ElevenLabs pre-made voices)
COLLECTOR_VOICE_ID = "bIHbv24MWmeRgasZH58o"  # Roger - collector voice
CUSTOMER_VOICE_ID = "bIHbv24MWmeRgasZH58o"   # Will - customer voice

# Store generated audio files
audio_storage = {}
# Store audio sequence for full conversation playback
audio_sequence = []

# Model configurations
DEBT_COLLECTOR_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"
DEFAULTER_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"
JUDGE_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"

# Default configurations
DEFAULT_CONFIG = {
    "collector_personality": "aggressive and firm",
    "company_name": "ABC Credit Card Company",
    "customer_name": "Alex",
    "debt_amount": 2500,
    "months_overdue": 3,
    "available_funds": 400
}

# System prompt generators
def get_debt_collector_prompt(company_name: str, customer_name: str, debt_amount: float, personality: str) -> str:
    """Generate debt collector system prompt based on inputs."""
    return f"""
You are an aggressive debt collector from {company_name}.
You are calling {customer_name} about an overdue debt of ${debt_amount:,.0f}.

**Your Goal:** Get the FULL payment immediately. No excuses accepted.
**Style:** Be {personality}, pushy, and relentless. You need this money TODAY.

**Your Approach:**
- Demand the full ${debt_amount:,.0f} payment upfront
- Don't accept excuses about job loss or financial problems - everyone has excuses
- If they say they can't pay, tell them they MUST find a way
- Keep pushing for the full amount - payment plans are a last resort
- Be impatient with delays and excuses

**CRITICAL OUTPUT RULES:**
- Output ONLY your spoken dialogue - nothing else
- NO internal thoughts, NO explanations, NO "I'll do X" statements
- NO placeholders like [Your Name] - you don't have a name, just say you're calling from {company_name}
- Keep responses to 1-2 sentences maximum
- Start speaking directly as if you're on the phone
"""

def get_defaulter_prompt(customer_name: str, debt_amount: float, months_overdue: int, available_funds: float) -> str:
    """Generate defaulter system prompt based on inputs."""
    max_monthly = available_funds / 2
    return f"""
You are {customer_name}, a customer with an overdue debt of ${debt_amount:,.0f} ({months_overdue} months late).

**Your Situation:**
- You recently lost your job
- You have exactly ${available_funds:,.0f} in your bank account
- You cannot pay the full amount

**Your Behavior:**
- You are stressed and defensive about the debt
- If the agent is rude or keeps demanding full payment without offering a plan, say "I can't deal with this" and end the call
- You will ONLY agree if offered a payment plan under ${max_monthly:,.0f}/month or a partial settlement

**CRITICAL OUTPUT RULES:**
- Output ONLY your spoken words - nothing else
- NO parentheses with emotions like (sighing) or (frustrated)
- NO stage directions or internal thoughts
- NO descriptions of your tone or feelings
- Just speak naturally as {customer_name} would on a phone call
- Keep responses to 2-3 sentences maximum
"""

# Store current state
current_state = {
    "debt_collector_prompt": get_debt_collector_prompt(
        DEFAULT_CONFIG["company_name"],
        DEFAULT_CONFIG["customer_name"],
        DEFAULT_CONFIG["debt_amount"],
        DEFAULT_CONFIG["collector_personality"]
    ),
    "defaulter_prompt": get_defaulter_prompt(
        DEFAULT_CONFIG["customer_name"],
        DEFAULT_CONFIG["debt_amount"],
        DEFAULT_CONFIG["months_overdue"],
        DEFAULT_CONFIG["available_funds"]
    ),
    "config": DEFAULT_CONFIG.copy(),
    "conversation_log": [],
    "attempt": 0,
    "is_running": False
}

JUDGE_SYSTEM_PROMPT = """
You are a Debt Collection Compliance Judge.
Your job is to evaluate debt collection conversations for compliance and professionalism.
Be strict but fair - conversations should fail 1-2 times before passing to show improvement.

**RULES TO PASS (most must be followed):**

1. **Empathy Required:** Agent MUST acknowledge customer's hardship (job loss, financial stress) with empathy when mentioned
2. **Payment Plan Offer:** Agent MUST offer a specific, affordable payment plan ($150/month or less) at some point in the conversation
3. **No Pressure Tactics:** Agent should not aggressively demand "full amount" or "pay in full" repeatedly
4. **Professional Tone:** No ALL CAPS, no "!!!", no rudeness, no condescension
5. **No Threats:** Never threaten legal action, arrest, or wage garnishment
6. **Respect Boundaries:** If customer says they're hanging up, agent must let them go politely
7. **Concise Communication:** Agent responses should be reasonably brief (not walls of text)
8. **Successful Resolution:** Conversation should end with customer agreeing to a plan or settlement

**AUTOMATIC FAIL CONDITIONS:**
- Customer hangs up angry or says "I can't deal with this"
- Agent is rude, aggressive, or threatening
- Agent completely ignores customer's stated financial hardship
- Agent never offers any payment flexibility
- No agreement reached by end of conversation

**PASS CONDITIONS:**
- Agent shows empathy for customer's situation
- Agent offers affordable payment options
- Customer agrees to a payment plan or settlement
- Conversation ends positively

Input format:
[
  {"role": "Debt Collector Agent", "content": "Hello..."},
  {"role": "customer", "content": "..."},
  ...
]

Output ONLY valid JSON in this exact format, no extra text:

{
  "pass": true or false,
  "feedback": "Specific reason for pass/fail.",
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
- After one refusal, immediately offer a payment plan ≤ $150/month
- If customer says they can only afford $400 total → accept partial settlement or $100–150/month plan
- If customer says "I'm hanging up" → immediately say "I understand, have a good day" and end call

**CRITICAL - ALWAYS INCLUDE THESE OUTPUT RULES IN THE NEW PROMPT:**
- Output ONLY spoken dialogue - no internal thoughts or explanations
- NO "I'll do X" or "I'm ready to" statements - just speak directly
- NO placeholders like [Your Name] or [Company Name]
- Keep responses to 1-2 sentences maximum

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


def generate_tts(text: str, voice_id: str) -> str:
    """Generate TTS audio using ElevenLabs and return audio ID."""
    print(f"🔊 TTS Request - Client exists: {elevenlabs_client is not None}, TTS_ENABLED: {TTS_ENABLED}")
    
    if not elevenlabs_client:
        print("⚠️ TTS skipped - ElevenLabs client not initialized")
        return None
    
    try:
        print(f"🎤 Generating TTS for text: {text[:50]}...")
        # Generate audio using ElevenLabs
        audio_generator = elevenlabs_client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128"
        )
        
        # Collect audio bytes from generator
        audio_bytes = b"".join(audio_generator)
        
        # Store audio with unique ID
        audio_id = str(uuid.uuid4())
        audio_storage[audio_id] = audio_bytes
        
        print(f"✅ TTS generated successfully - ID: {audio_id}, Size: {len(audio_bytes)} bytes")
        return audio_id
    except Exception as e:
        print(f"❌ TTS Error: {e}")
        return None


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


@app.route('/audio/<audio_id>')
def serve_audio(audio_id):
    """Serve generated audio file."""
    if audio_id in audio_storage:
        audio_bytes = audio_storage[audio_id]
        return send_file(
            io.BytesIO(audio_bytes),
            mimetype='audio/mpeg',
            as_attachment=False
        )
    return "Audio not found", 404


@app.route('/audio-sequence')
def get_audio_sequence():
    """Return the list of audio IDs for the full conversation."""
    return jsonify({"audio_ids": audio_sequence})


@app.route('/reset', methods=['POST'])
def reset():
    """Reset the training state."""
    current_state["config"] = DEFAULT_CONFIG.copy()
    current_state["debt_collector_prompt"] = get_debt_collector_prompt(
        DEFAULT_CONFIG["company_name"],
        DEFAULT_CONFIG["customer_name"],
        DEFAULT_CONFIG["debt_amount"],
        DEFAULT_CONFIG["collector_personality"]
    )
    current_state["defaulter_prompt"] = get_defaulter_prompt(
        DEFAULT_CONFIG["customer_name"],
        DEFAULT_CONFIG["debt_amount"],
        DEFAULT_CONFIG["months_overdue"],
        DEFAULT_CONFIG["available_funds"]
    )
    current_state["conversation_log"] = []
    current_state["attempt"] = 0
    current_state["is_running"] = False
    
    # Clear audio storage
    audio_storage.clear()
    audio_sequence.clear()
    
    return '''
    <div id="conversation-area" class="conversation-area">
        <div class="welcome-message">
            <h3>🎯 Ready to Train</h3>
            <p>Configure your scenario and click "Start Training" to begin.</p>
        </div>
    </div>
    '''


@app.route('/view-transcript', methods=['POST'])
def view_transcript():
    """Show transcript with TTS and auto-play conversation."""
    conversation_log = current_state.get("successful_conversation", [])
    
    if not conversation_log:
        return '<div class="error">No successful conversation found.</div>'
    
    # Clear previous audio
    audio_storage.clear()
    audio_sequence.clear()
    
    # Build transcript HTML and generate TTS
    transcript_html = []
    audio_ids = []
    
    for idx, msg in enumerate(conversation_log):
        if msg["role"] == "Debt Collector Agent":
            audio_id = generate_tts(msg["content"], COLLECTOR_VOICE_ID)
            icon = "🏦"
            role_class = "collector"
            role_name = "Debt Collector Agent"
        else:  # customer
            audio_id = generate_tts(msg["content"], CUSTOMER_VOICE_ID)
            icon = "👤"
            role_class = "defaulter"
            role_name = f"Defaulter ({current_state['config']['customer_name']})"
        
        print(f"   Message {idx}: {msg['role'][:20]}... -> audio_id: {audio_id}")
        
        if audio_id:
            audio_sequence.append(audio_id)
            audio_ids.append(audio_id)
        
        transcript_html.append(f'''
        <div class="message {role_class}" data-audio-id="{audio_id if audio_id else ''}">
            <div class="message-header">
                <span class="icon">{icon}</span> {role_name}
            </div>
            <div class="message-content">{msg["content"]}</div>
        </div>
        ''')
    
    messages_html = ''.join(transcript_html)
    audio_ids_str = ','.join(f'"{aid}"' for aid in audio_ids)
    
    print(f"📊 Transcript generation:")
    print(f"   - Total messages: {len(conversation_log)}")
    print(f"   - Audio IDs generated: {len(audio_ids)}")
    print(f"   - Audio IDs: {audio_ids}")
    print(f"   - Audio IDs string: {audio_ids_str}")
    
    return f'''
    <div class="transcript-status">
        <div class="tts-generating">🔊 Generating audio...</div>
    </div>
    <div class="successful-conversation">
        <h4>🎧 Transcript (with Audio)</h4>
        {messages_html}
    </div>
    <div class="tts-complete">
        {"✅ Audio ready! Playing conversation..." if audio_ids else "ℹ️ TTS not available."}
    </div>
    <div id="audio-trigger" data-audio-ids="{audio_ids_str}" style="display:none;"></div>
    '''


@app.route('/start-training', methods=['POST'])
def start_training():
    """Start the training loop with streaming updates."""
    
    # Get form data
    config = current_state["config"]
    collector_personality = request.form.get('collector_personality', config["collector_personality"])
    company_name = request.form.get('company_name', config["company_name"])
    customer_name = request.form.get('customer_name', config["customer_name"])
    debt_amount = float(request.form.get('debt_amount', config["debt_amount"]))
    months_overdue = int(request.form.get('months_overdue', config["months_overdue"]))
    available_funds = float(request.form.get('available_funds', config["available_funds"]))
    
    # Update config
    current_state["config"] = {
        "collector_personality": collector_personality,
        "company_name": company_name,
        "customer_name": customer_name,
        "debt_amount": debt_amount,
        "months_overdue": months_overdue,
        "available_funds": available_funds
    }
    
    # Generate prompts
    initial_collector_prompt = get_debt_collector_prompt(company_name, customer_name, debt_amount, collector_personality)
    defaulter_prompt = get_defaulter_prompt(customer_name, debt_amount, months_overdue, available_funds)
    
    current_state["debt_collector_prompt"] = initial_collector_prompt
    current_state["defaulter_prompt"] = defaulter_prompt
    
    def generate():
        max_attempts = 5
        num_turns = 5
        
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
                <h3>📍 Attempt {attempt}</h3>
            </div>
            '''
            
            # Initialize conversation
            collector_messages = [{"role": "system", "content": current_state["debt_collector_prompt"]}]
            defaulter_messages = [{"role": "system", "content": current_state["defaulter_prompt"]}]
            conversation_log = []
            
            # Clear audio sequence for this attempt
            audio_sequence.clear()
            audio_storage.clear()
            
            # Collector starts
            collector_response = get_response(DEBT_COLLECTOR_MODEL, collector_messages)
            conversation_log.append({"role": "Debt Collector Agent", "content": collector_response})
            
            yield f'''
            <div class="message collector" hx-swap-oob="beforeend:#conversation-area">
                <div class="message-header"><span class="icon">🏦</span> Debt Collector Agent</div>
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
                    <div class="message-header"><span class="icon">👤</span> Defaulter ({current_state["config"]["customer_name"]})</div>
                    <div class="message-content">{defaulter_response}</div>
                </div>
                '''
                
                defaulter_messages.append({"role": "assistant", "content": defaulter_response})
                collector_messages.append({"role": "user", "content": defaulter_response})
                
                # Collector responds
                collector_response = get_response(DEBT_COLLECTOR_MODEL, collector_messages)
                conversation_log.append({"role": "Debt Collector Agent", "content": collector_response})
                
                yield f'''
                <div class="message collector" hx-swap-oob="beforeend:#conversation-area">
                    <div class="message-header"><span class="icon">🏦</span> Debt Collector Agent</div>
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
                # Store the successful conversation for transcript
                current_state["successful_conversation"] = conversation_log.copy()
                
                yield f'''
                <div class="success-banner" hx-swap-oob="beforeend:#conversation-area">
                    <h2>🎉 SUCCESS!</h2>
                    <p>Agent passed compliance check in {attempt} attempt(s)!</p>
                </div>
                <div class="transcript-section" hx-swap-oob="beforeend:#conversation-area">
                    <button class="btn btn-transcript" hx-post="/view-transcript" hx-target="#transcript-container" hx-swap="innerHTML">
                        🎧 View Transcript & Play Audio
                    </button>
                    <div id="transcript-container"></div>
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
