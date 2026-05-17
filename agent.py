import os
import certifi

# Fix for macOS SSL Certificate errors - MUST be before other imports
os.environ['SSL_CERT_FILE'] = certifi.where()

import logging
import json
import asyncio
import httpx
from dotenv import load_dotenv

from livekit import agents, api
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import (
    openai,
    cartesia,
    deepgram,
    noise_cancellation,
    silero,
    sarvam,
)
from livekit.agents import llm
from typing import Annotated, Optional

# Load environment variables
load_dotenv(".env")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("outbound-agent")

import config

# TRUNK ID - Now loaded from config.py
# You can find this by running 'python setup_trunk.py --list' or checking LiveKit Dashboard 


def _build_tts(config_provider: str = None, config_voice: str = None):
    """Configure the Text-to-Speech provider based on env vars or dynamic config."""
    # Priority: Config > Env Var > Default
    provider = (config_provider or os.getenv("TTS_PROVIDER", config.DEFAULT_TTS_PROVIDER)).lower()
    print(f"\n==============================================")
    print(f"DEBUG: TTS_PROVIDER selected is -> {provider}")
    print(f"DEBUG: Voice ID requested is -> {config_voice}")
    print(f"DEBUG: OPENAI_API_KEY present? -> {'Yes' if os.getenv('OPENAI_API_KEY') else 'No'}")
    print(f"==============================================\n")
    
    # If using Sarvam Voice names (Anushka/Aravind), force Sarvam provider
    if config_voice in ["anushka", "aravind", "amartya", "dhruv"]:
        provider = "sarvam"

    if provider == "cartesia":
        logger.info("Using Cartesia TTS")
        model = os.getenv("CARTESIA_TTS_MODEL", config.CARTESIA_MODEL)
        voice = os.getenv("CARTESIA_TTS_VOICE", config.CARTESIA_VOICE)
        return cartesia.TTS(model=model, voice=voice)
    
    if provider == "sarvam":
        logger.info(f"Using Sarvam TTS (Voice: {config_voice})")
        model = os.getenv("SARVAM_TTS_MODEL", config.SARVAM_MODEL)
        # Use dynamic voice or env var or default
        # Ignore OpenAI specific voices
        valid_sarvam_voices = ["shubh", "ritu", "rahul", "pooja", "simran", "kavya", "amit", "ratan", "rohan", "dev", "ishita", "shreya", "manan", "sumit", "priya", "aditya", "kabir", "neha", "varun", "roopa", "aayan", "ashutosh", "advait", "amelia", "sophia", "anushka", "aravind"]
        voice = config_voice if config_voice in valid_sarvam_voices else os.getenv("SARVAM_VOICE", "amit")
        language = os.getenv("SARVAM_LANGUAGE", config.SARVAM_LANGUAGE)
        return sarvam.TTS(model=model, speaker=voice, target_language_code=language)

    if provider == "deepgram":
        logger.info("Using Deepgram TTS")
        model = os.getenv("DEEPGRAM_TTS_MODEL", "aura-asteria-en")
        return deepgram.TTS(model=model)

    # Default to OpenAI
    logger.info(f"Using OpenAI TTS (Voice: {config_voice})")
    model = os.getenv("OPENAI_TTS_MODEL", "tts-1")
    voice = config_voice or os.getenv("OPENAI_TTS_VOICE", config.DEFAULT_TTS_VOICE)
    return openai.TTS(model=model, voice=voice)


def _build_llm(config_provider: str = None):
    """Configure the LLM provider based on config or env vars."""
    provider = (config_provider or os.getenv("LLM_PROVIDER", config.DEFAULT_LLM_PROVIDER)).lower()

    if provider == "groq":
        logger.info("Using Groq LLM")
        return openai.LLM(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY"),
            model=os.getenv("GROQ_MODEL", config.GROQ_MODEL),
            temperature=float(os.getenv("GROQ_TEMPERATURE", str(config.GROQ_TEMPERATURE))),
        )
    
    # Default to OpenAI
    logger.info("Using OpenAI LLM")
    return openai.LLM(model=config.DEFAULT_LLM_MODEL)



class TransferFunctions(llm.ToolContext):
    def __init__(self, ctx: agents.JobContext, phone_number: str = None, dashboard_url: str = None, lead_id: str = None):
        super().__init__(tools=[])
        self.ctx = ctx
        self.phone_number = phone_number
        self.dashboard_url = dashboard_url
        self.lead_id = lead_id

    @llm.function_tool(description="End the call. Use this when the customer says they are not interested, they already have a website, or they just want to hang up.")
    async def not_interested(self):
        logger.info("Customer not interested. Ending call.")
        self.call_ended_by_tool = True
        if self.dashboard_url and self.lead_id:
            try:
                # Fire and forget dashboard update
                asyncio.ensure_future(_notify_dashboard(self.dashboard_url, self.lead_id, "not_confirmed"))
            except Exception as e:
                logger.error(f"Error in notify: {e}")
                
        # Drop the call
        async def _delayed_shutdown():
            await asyncio.sleep(4) # Give agent time to say bye
            self.ctx.shutdown()
            
        asyncio.ensure_future(_delayed_shutdown())
        return "Call ending sequence initiated. EXACTLY say: 'Thank you, aapka din shubh ho.' and then wait."

    @llm.function_tool(description="Confirm demo and record the verified 10-digit WhatsApp number. ONLY call this AFTER the user has explicitly provided/confirmed a 10-digit WhatsApp number and agreed to the demo.")
    async def confirm_demo(self, whatsapp_number: str):
        logger.info(f"Demo confirmed. WhatsApp Number: {whatsapp_number}")
        self.call_ended_by_tool = True
        if self.dashboard_url and self.lead_id:
            try:
                # Dashboard update
                async def _update_demo():
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        url = f"{self.dashboard_url}/api/leads/{self.lead_id}"
                        payload = {"status": "demo_confirmed", "whatsapp_number": whatsapp_number}
                        await client.patch(url, json=payload)
                asyncio.ensure_future(_update_demo())
            except Exception as e:
                logger.error(f"Failed to notify dashboard of demo confirmation: {e}")
        
        # End call after confirming
        async def _delayed_shutdown():
            await asyncio.sleep(4) # Let agent say thank you
            self.ctx.shutdown()
            
        asyncio.ensure_future(_delayed_shutdown())
        return "Demo confirmed successfully. EXACTLY say: 'Thank you, main aapko WhatsApp par demo bhej raha hoon. Aapka din shubh ho.' and then wait."

    @llm.function_tool(description="Look up user details by phone number.")
    def lookup_user(self, phone: str):
        """
        Mock function to look up user details.

        Args:
            phone: The phone number to look up
        """
        logger.info(f"Looking up user: {phone}")
        return f"User found: Shreyas Raj. Status: Premium. Last order: Coffee setup (Delivered)."

    @llm.function_tool(description="Transfer the call to a human support agent or another phone number.")
    async def transfer_call(self, destination: Optional[str] = None):
        """
        Transfer the call.
        """
        if destination is None:
            destination = config.DEFAULT_TRANSFER_NUMBER
            if not destination:
                 return "Error: No default transfer number configured."
        if "@" not in destination:
            # If no domain is provided, append the SIP domain
            if config.SIP_DOMAIN:
                # Ensure clean number (strip tel: or sip: prefix if present but no domain)
                clean_dest = destination.replace("tel:", "").replace("sip:", "")
                destination = f"sip:{clean_dest}@{config.SIP_DOMAIN}"
            else:
                # Fallback to tel URI if no domain configured
                if not destination.startswith("tel:") and not destination.startswith("sip:"):
                     destination = f"tel:{destination}"
        elif not destination.startswith("sip:"):
             destination = f"sip:{destination}"
        
        logger.info(f"Transferring call to {destination}")
        
        # Determine the participant identity
        # For outbound calls initiated by this agent, the participant identity is typically "sip_<phone_number>"
        # For inbound, we might need to find the remote participant.
        participant_identity = None
        
        # If we stored the phone number from metadata, we can construct the identity
        if self.phone_number:
            participant_identity = f"sip_{self.phone_number}"
        else:
            # Try to find a participant that is NOT the agent
            for p in self.ctx.room.remote_participants.values():
                participant_identity = p.identity
                break
        
        if not participant_identity:
            logger.error("Could not determine participant identity for transfer")
            return "Failed to transfer: could not identify the caller."

        try:
            logger.info(f"Transferring participant {participant_identity} to {destination}")
            await self.ctx.api.sip.transfer_sip_participant(
                api.TransferSIPParticipantRequest(
                    room_name=self.ctx.room.name,
                    participant_identity=participant_identity,
                    transfer_to=destination,
                    play_dialtone=False
                )
            )
            return "Transfer initiated successfully."
        except Exception as e:
            logger.error(f"Transfer failed: {e}")
            return f"Error executing transfer: {e}"


class OutboundAssistant(Agent):
    """
    An AI agent tailored for outbound calls.
    Attempts to be helpful and concise.
    """
    def __init__(self, tools: list, instructions: str) -> None:
        super().__init__(
            instructions=instructions,
            tools=tools,
        )




async def _notify_dashboard(dashboard_url: str, lead_id: str, status: str, duration: int = 0):
    """Notify the dashboard that a call has ended and update lead status."""
    if not dashboard_url or not lead_id:
        logger.warning(f"Cannot notify dashboard: url={dashboard_url}, lead_id={lead_id}")
        return
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Update lead status
            url = f"{dashboard_url}/api/leads/{lead_id}"
            payload = {"status": status}
            logger.info(f"Notifying dashboard: {url} -> {status}")
            resp = await client.patch(url, json=payload)
            logger.info(f"Dashboard response: {resp.status_code}")
    except Exception as e:
        logger.error(f"Failed to notify dashboard: {e}")


async def entrypoint(ctx: agents.JobContext):
    """
    Main entrypoint for the agent.
    
    For outbound calls:
    1. Checks for 'phone_number' in the job metadata.
    2. Connects to the room.
    3. Initiates the SIP call to the phone number.
    4. Waits for answer before speaking.
    """
    logger.info(f"Connecting to room: {ctx.room.name}")
    
    # parse the phone number AND config from the metadata
    phone_number = None
    lead_id = None
    business_name = None
    dashboard_url = "http://localhost:3000"
    config_dict = {}
    call_answered = False
    
    # Check Job Metadata (Legacy/Dispatch)
    try:
        if ctx.job.metadata:
            data = json.loads(ctx.job.metadata)
            phone_number = data.get("phone_number")
            lead_id = data.get("lead_id")
            business_name = data.get("business_name")
            dashboard_url = data.get("dashboard_url", dashboard_url)
            config_dict = data
    except Exception:
        pass
        
    # Check Room Metadata (Dashboard/Route.ts) - Overrides Job Metadata if present
    try:
        if ctx.room.metadata:
            data = json.loads(ctx.room.metadata)
            if data.get("phone_number"):
                phone_number = data.get("phone_number")
            if data.get("lead_id"):
                lead_id = data.get("lead_id")
            if data.get("business_name"):
                business_name = data.get("business_name")
            if data.get("dashboard_url"):
                dashboard_url = data.get("dashboard_url")
            config_dict.update(data) # Merge configs
    except Exception:
        logger.warning("No valid JSON metadata found in Room.")
    
    logger.info(f"Call config: phone={phone_number}, lead_id={lead_id}, business_name={business_name}, dashboard={dashboard_url}")

    # Initialize function context
    fnc_ctx = TransferFunctions(ctx, phone_number, dashboard_url, lead_id)

    # Resilient configuration fetching
    m_provider = config_dict.get("model_provider") or os.getenv("LLM_PROVIDER") or config.DEFAULT_LLM_PROVIDER
    tts_provider = config_dict.get("tts_provider") or os.getenv("TTS_PROVIDER") or config.DEFAULT_TTS_PROVIDER
    m_voice = config_dict.get("voice_id") or os.getenv("OPENAI_TTS_VOICE") or config.DEFAULT_TTS_VOICE
    
    print(f"--- BOOM: Initializing with LLM Provider: {m_provider}, TTS Provider: {tts_provider}, Voice: {m_voice} ---")

    # Initialize the Agent Session with plugins
    try:
        session = AgentSession(
            vad=silero.VAD.load(min_silence_duration=0.3, min_speech_duration=0.1),
            stt=deepgram.STT(model=config.STT_MODEL, language=config.STT_LANGUAGE, interim_results=True), 
            llm=_build_llm(m_provider),
            tts=_build_tts(tts_provider, m_voice),
        )
        print("--- BOOM: Session Object Created ---")
    except Exception as e:
        print(f"--- BOOM CRITICAL ERROR: Session Init Failed: {e} ---")
        # Extreme fallback to OpenAI defaults
        session = AgentSession(
            vad=silero.VAD.load(min_silence_duration=0.3),
            stt=deepgram.STT(model="nova-2", language="hi"),
            llm=openai.LLM(),
            tts=openai.TTS(),
        )

    # Build dynamic instructions
    system_prompt = config.SYSTEM_PROMPT
    if business_name:
        system_prompt += f"\n\n## TARGET BUSINESS DETAILS (VERY IMPORTANT):\n- You are calling a business named: '{business_name}'\n- As soon as the call connects, you MUST first confirm if you are talking to the representative of '{business_name}' by saying: 'गुड मॉर्निंग सर, क्या मैं {business_name} से बात कर रहा हूँ?'"

    # Start the session
    print("--- BOOM: Starting Session ---")
    await session.start(
        room=ctx.room,
        agent=OutboundAssistant(tools=list(fnc_ctx.function_tools.values()), instructions=system_prompt),
    )
    print("--- BOOM: Session Started Successfully ---")

    # Listen for transcript events for debugging
    @session.on("user_speech_committed")
    def on_user_speech(msg: llm.ChatMessage):
        if msg.content:
            logger.info(f"USER: {msg.content}")
            print(f"\n--- BOOM USER SAID: {msg.content} ---")

    @session.on("agent_speech_committed")
    def on_agent_speech(msg: llm.ChatMessage):
        if msg.content:
            logger.info(f"AGENT: {msg.content}")
            print(f"--- BOOM AGENT SAID: {msg.content} ---\n")
            
            # --- FAIL-SAFE CALL HANGUP ---
            # Agar LLM tool call karna bhool jaye, par Nitin farewell bol de, toh call 4s me cut ho jayegi
            content_lower = msg.content.lower()
            farewell_phrases = [
                "shubh ho", "शुभ हो", 
                "demo bhej", "डेमो भेज", 
                "keemti samay", "कीमती समय", 
                "great day", "ग्रेट डे",
                "thank you, main aapko whatsapp",
                "aapka din shubh"
            ]
            if any(phrase in content_lower for phrase in farewell_phrases):
                print("--- [FAIL-SAFE] Farewell detected! Hanging up call in 4 seconds... ---")
                async def _fail_safe_shutdown():
                    await asyncio.sleep(4.0)
                    print("--- [FAIL-SAFE] Shutting down room session now! ---")
                    ctx.shutdown()
                asyncio.ensure_future(_fail_safe_shutdown())

    should_dial = False
    if phone_number:
        # Check if any remote participant looks like our user (sip_PHONE)
        user_already_here = False
        for p in ctx.room.remote_participants.values():
            if f"sip_{phone_number}" in p.identity or "sip_" in p.identity:
                user_already_here = True
                break
        
        if not user_already_here:
            should_dial = True
            logger.info("User not in room. Agent will initiate dial-out.")
        else:
            logger.info("User already in room (Dashboard dispatched). output Only generated greeting.")

    if should_dial:
        # Clean phone number: remove spaces, dashes, and ensure only digits
        dial_number = "".join(filter(str.isdigit, phone_number))
        
        print(f"[TRACE] Dialing {dial_number} on trunk {config.SIP_TRUNK_ID}")
        try:
            await ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=ctx.room.name,
                    sip_trunk_id=config.SIP_TRUNK_ID,
                    sip_call_to=dial_number,
                    participant_identity=f"sip_{dial_number}",
                    wait_until_answered=True,
                )
            )
            print("[TRACE] Call picked up or ringing ended!")
            call_answered = True
            
            # Wait for the participant to actually appear in the room
            print("[TRACE] Waiting for participant to appear in Room context...")
            for _ in range(20):
                if any(f"sip_{dial_number}" in p.identity for p in ctx.room.remote_participants.values()):
                    print("[TRACE] Participant fully joined the Room!")
                    break
                print("[TRACE] Still waiting for SIP participant object...")
                await asyncio.sleep(0.5)
            
            # --- CALL END DETECTION ---
            # Listen for participant disconnect to update dashboard
            @ctx.room.on("participant_disconnected")
            def on_participant_left(participant):
                if "sip_" in participant.identity:
                    logger.info(f"SIP participant {participant.identity} disconnected - call ended")
                    print(f"--- BOOM: Call ended, participant {participant.identity} left ---")
                    # Schedule the dashboard notification only if we didn't explicitly end it via a tool
                    if not getattr(fnc_ctx, 'call_ended_by_tool', False):
                        asyncio.ensure_future(
                            _notify_dashboard(dashboard_url, lead_id, "not_confirmed")
                        )
                    # Shutdown after a short delay to let notification go through
                    async def _delayed_shutdown():
                        await asyncio.sleep(2)
                        ctx.shutdown()
                    asyncio.ensure_future(_delayed_shutdown())
            
            print("[TRACE] Sleeping 2.0s to let SIP audio channel initialize...")
            await asyncio.sleep(2.0)
            
            # Construct greeting dynamically if business_name is available
            greeting = config.INITIAL_GREETING
            if business_name:
                greeting = f"गुड मॉर्निंग सर, क्या मैं {business_name} से बात कर रहा हूँ? मेरा नाम नितिन है, और ये एक मार्केटिंग कॉल है, हम बिज़नेस के लिए वेबसाइट बनाते हैं, मैं बस आपके 30 सेकंड्स लूँगा.."
                
            try:
                if hasattr(session, "say"):
                    print(f"[TRACE] Calling session.say() with allow_interruptions=False")
                    # Set allow_interruptions to False so background noise doesn't immediately cut it off!
                    if asyncio.iscoroutinefunction(session.say):
                        await session.say(greeting, allow_interruptions=False)
                    else:
                        session.say(greeting, allow_interruptions=False)
                    print("[TRACE] session.say() executed successfully.")
                elif hasattr(session, "generate_reply"):
                    print("--- BOOM: Calling session.generate_reply() ---")
                    if asyncio.iscoroutinefunction(session.generate_reply):
                        await session.generate_reply(instructions=greeting)
                    else:
                        session.generate_reply(instructions=greeting)
                else:
                    print("--- BOOM: Pushing system message to LLM ---")
                    session.push_message(llm.ChatMessage(role="system", content=f"Call started. Greet the user now: {greeting}"))
            except Exception as e:
                import traceback
                print(f"--- BOOM ERROR IN GREETING: {e} ---")
                traceback.print_exc()
            
            print("--- BOOM: Greet logic finished ---")
            
        except Exception as e:
            logger.error(f"Failed to place outbound call: {e}")
            # Call failed - update status to no_answer
            await _notify_dashboard(dashboard_url, lead_id, "no_answer")
            ctx.shutdown()
    else:
        # Fallback for inbound calls (if this agent is used for that) OR Dashboard calls where user is already there
        logger.info("Detecting if we should greet...")
        if asyncio.iscoroutinefunction(session.generate_reply):
            await session.generate_reply(instructions=config.fallback_greeting)
        else:
            session.generate_reply(instructions=config.fallback_greeting)


import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer

def run_dummy_server():
    class DummyHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"LiveKit Agent is running and active!")
            
        def log_message(self, format, *args):
            # Suppress logs to avoid cluttering agent logs
            pass

    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    logger.info(f"Starting dummy HTTP server on port {port} for Render keep-alive...")
    server.serve_forever()


if __name__ == "__main__":
    # Start dummy web server in a background thread
    t = threading.Thread(target=run_dummy_server, daemon=True)
    t.start()

    # The agent name "outbound-caller" is used by the dispatch script to find this worker
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="outbound-caller", 
        )
    )
