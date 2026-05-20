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
logging.basicConfig(level=logging.DEBUG)
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
        language = os.getenv("CARTESIA_LANGUAGE", config.CARTESIA_LANGUAGE)
        print(f"DEBUG: Using Cartesia with model={model}, voice={voice}, language={language}")
        return cartesia.TTS(model=model, voice=voice, language=language)
    
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
        # Check if the voice name is a valid Deepgram voice (usually starts with aura-)
        voice = config_voice if config_voice and config_voice.startswith("aura-") else os.getenv("DEEPGRAM_TTS_MODEL", config.DEFAULT_TTS_VOICE)
        logger.info(f"Using Deepgram TTS (Voice: {voice})")
        return deepgram.TTS(model=voice)

    # Default to OpenAI
    logger.info(f"Using OpenAI TTS (Voice: {config_voice})")
    model = os.getenv("OPENAI_TTS_MODEL", "tts-1")
    voice = config_voice or os.getenv("OPENAI_TTS_VOICE", config.DEFAULT_TTS_VOICE)
    return openai.TTS(model=model, voice=voice)


def _build_llm(config_provider: str = None):
    """Configure the LLM provider based on config or env vars. Strictly forces Groq."""
    
    logger.info("Using Groq LLM (Enforced)")
    return openai.LLM(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.getenv("GROQ_API_KEY"),
        model=os.getenv("GROQ_MODEL", config.GROQ_MODEL),
        temperature=float(os.getenv("GROQ_TEMPERATURE", str(config.GROQ_TEMPERATURE))),
    )



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
                
        # Drop the call immediately after thank you
        async def _delayed_shutdown():
            await asyncio.sleep(2)
            self.ctx.shutdown()
            
        asyncio.ensure_future(_delayed_shutdown())
        return "EXACTLY say: 'Ok sir, koi baat nahi. Thank you, aapka din shubh ho.' and then wait silently."

    @llm.function_tool(description="CRITICAL: Only call this AFTER you have explained the free demo website offer AND the customer explicitly says they want to see the demo on WhatsApp. Do NOT call this when they are just confirming their name. WhatsApp number is optional.")
    async def confirm_demo(self, whatsapp_number: Optional[str] = None):
        logger.info(f"Demo confirmed. WhatsApp Number: {whatsapp_number or 'same as call number'}")
        self.call_ended_by_tool = True
        # Use call number as fallback if no WhatsApp number given
        wa_number = whatsapp_number or self.phone_number or ""
        if self.dashboard_url and self.lead_id:
            try:
                # Dashboard update
                async def _update_demo():
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        url = f"{self.dashboard_url}/api/leads/{self.lead_id}"
                        payload = {"status": "demo_confirmed", "whatsapp_number": wa_number}
                        await client.patch(url, json=payload)
                asyncio.ensure_future(_update_demo())
            except Exception as e:
                logger.error(f"Failed to notify dashboard of demo confirmation: {e}")
        
        # End call after thank you
        async def _delayed_shutdown():
            await asyncio.sleep(3)
            self.ctx.shutdown()
            
        asyncio.ensure_future(_delayed_shutdown())
        return "EXACTLY say: 'Bilkul sir, main thode der mein aapki demo website aapke WhatsApp par bhej dunga. Thank you, aapka din shubh ho!' and then wait silently."

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


async def _start_recording(ctx: agents.JobContext, phone_number: str, lead_id: str = None) -> str | None:
    """
    Jab customer call uthaye, LiveKit Egress API se recording start karo.
    Recording Cloudflare R2 mein save hogi.
    Returns: egress_id (recording stop karne ke liye) ya None agar recording disabled ho
    """
    if os.getenv("ENABLE_RECORDING", "false").lower() != "true":
        logger.info("Recording disabled (ENABLE_RECORDING != true)")
        return None

    r2_access_key = os.getenv("R2_ACCESS_KEY_ID", "")
    r2_secret = os.getenv("R2_SECRET_ACCESS_KEY", "")
    r2_account_id = os.getenv("R2_ACCOUNT_ID", "")
    r2_bucket = os.getenv("R2_BUCKET_NAME", "livekit-recordings")

    if not r2_access_key or r2_access_key == "your_r2_access_key_here":
        logger.warning("R2 credentials not configured — recording skipped. Fill in .env file.")
        return None

    try:
        from livekit.protocol import egress as egress_proto

        # Safe filename: phone number + timestamp
        import re
        from datetime import datetime, timezone, timedelta
        ist = timezone(timedelta(hours=5, minutes=30))
        timestamp = datetime.now(ist).strftime("%Y%m%d_%H%M%S")
        safe_phone = re.sub(r'[^0-9]', '', phone_number or "unknown")
        lead_suffix = f"_{lead_id}" if lead_id else ""
        file_name = f"calls/{safe_phone}{lead_suffix}_{timestamp}.mp4"

        # Cloudflare R2 endpoint
        r2_endpoint = f"https://{r2_account_id}.r2.cloudflarestorage.com"

        s3_upload = egress_proto.S3Upload(
            access_key=r2_access_key,
            secret=r2_secret,
            bucket=r2_bucket,
            endpoint=r2_endpoint,
            force_path_style=True,
            region="auto",
        )

        file_output = egress_proto.EncodedFileOutput(
            filepath=file_name,
            s3=s3_upload,
        )

        request = egress_proto.RoomCompositeEgressRequest(
            room_name=ctx.room.name,
            layout="speaker",
            audio_only=True,   # Sirf audio chahiye (phone call hai)
            file=file_output,
        )

        lk_url = os.getenv("LIVEKIT_URL", "").replace("wss://", "https://").replace("ws://", "http://")
        lk_api_key = os.getenv("LIVEKIT_API_KEY", "")
        lk_api_secret = os.getenv("LIVEKIT_API_SECRET", "")

        lkapi = api.LiveKitAPI(lk_url, lk_api_key, lk_api_secret)
        egress_info = await lkapi.egress.start_room_composite_egress(request)
        await lkapi.aclose()

        logger.info(f"✅ Recording started! File: {file_name} | Egress ID: {egress_info.egress_id}")
        print(f"[RECORDING] Started → R2 bucket '{r2_bucket}' | File: {file_name}")
        return egress_info.egress_id

    except Exception as e:
        logger.error(f"Failed to start recording: {e}")
        print(f"[RECORDING ERROR] {e}")
        return None


async def _stop_recording(egress_id: str):
    """Recording band karo jab call khatam ho."""
    if not egress_id:
        return
    try:
        lk_url = os.getenv("LIVEKIT_URL", "").replace("wss://", "https://").replace("ws://", "http://")
        lk_api_key = os.getenv("LIVEKIT_API_KEY", "")
        lk_api_secret = os.getenv("LIVEKIT_API_SECRET", "")

        lkapi = api.LiveKitAPI(lk_url, lk_api_key, lk_api_secret)
        await lkapi.egress.stop_egress(api.StopEgressRequest(egress_id=egress_id))
        await lkapi.aclose()
        logger.info(f"✅ Recording stopped. Egress ID: {egress_id}")
        print(f"[RECORDING] Stopped → Egress ID: {egress_id}")
    except Exception as e:
        logger.error(f"Failed to stop recording: {e}")



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

    # Calculate time-based greeting for context injection
    from datetime import datetime, timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    hour = datetime.now(ist).hour
    if hour < 12:
        time_salutation = "गुड मॉर्निंग"
    elif hour < 17:
        time_salutation = "गुड आफ्टरनून"
    else:
        time_salutation = "गुड ईवनिंग"

    if business_name:
        greeting = f"{time_salutation} सर, क्या मैं {business_name} से बात कर रहा हूँ?"
    else:
        greeting = f"{time_salutation} सर, मेरा नाम नितिन है, हम बिज़नेस के लिए वेबसाइट बनाते हैं।"

    # Build dynamic instructions
    system_prompt = config.SYSTEM_PROMPT
    if business_name:
        system_prompt += f"\n\n## TARGET BUSINESS DETAILS:\n- You are calling a business named: '{business_name}'"

    # Start the session
    print("--- BOOM: Starting Session ---")
    await session.start(
        room=ctx.room,
        agent=OutboundAssistant(tools=list(fnc_ctx.function_tools.values()), instructions=system_prompt),
    )
    print("--- BOOM: Session Started Successfully ---")

    def _log_trace(msg_text):
        try:
            with open("live_debug.txt", "a", encoding="utf-8") as f:
                f.write(msg_text + "\n")
        except:
            pass

    # --- TRACE EVENT LISTENERS ADDED FOR DEBUGGING ---
    @session.on("state_changed")
    def on_state_changed(state):
        _log_trace(f"--- TRACE: Agent State Changed: {state} ---")
        
    @session.on("error")
    def on_error(error):
        _log_trace(f"--- TRACE ERROR: {error} ---")
        
    @session.on("user_speech_committed")
    def on_user_speech_trace(msg):
        _log_trace(f"--- TRACE: user_speech_committed: {msg} ---")
        
    @session.on("agent_speech_committed")
    def on_agent_speech_trace(msg):
        _log_trace(f"--- TRACE: agent_speech_committed: {msg} ---")
        
    @session.on("user_input_transcribed")
    def on_user_input_trace(ev):
        _log_trace(f"--- TRACE: user_input_transcribed: {ev} ---")
        
    @session.on("conversation_item_added")
    def on_conversation_item_trace(ev):
        _log_trace(f"--- TRACE: conversation_item_added: {ev} ---")
        
    @session.on("function_tools_executed")
    def on_function_tools_trace(ev):
        _log_trace(f"--- TRACE: function_tools_executed: {ev} ---")
    # --------------------------------------------------

    # Listen for transcript events for debugging
    @session.on("user_speech_committed")
    def on_user_speech(msg: llm.ChatMessage):
        if msg.content:
            logger.info(f"USER: {msg.content}")
            print(f"\n--- BOOM USER SAID: {msg.content} ---")
            with open("chat_debug.txt", "a", encoding="utf-8") as f:
                f.write(f"USER: {msg.content}\n")

    @session.on("agent_speech_committed")
    def on_agent_speech(msg: llm.ChatMessage):
        if msg.content:
            logger.info(f"AGENT: {msg.content}")
            print(f"--- BOOM AGENT SAID: {msg.content} ---\n")
            with open("chat_debug.txt", "a", encoding="utf-8") as f:
                f.write(f"AGENT: {msg.content}\n")
            
            # --- FAIL-SAFE CALL HANGUP ---
            # Agar LLM tool call karna bhool jaye, par Nitin farewell bol de, toh call 4s me cut ho jayegi
            content_text = ""
            if isinstance(msg.content, str):
                content_text = msg.content
            elif isinstance(msg.content, list):
                for item in msg.content:
                    if isinstance(item, str):
                        content_text += item
                    elif hasattr(item, 'text'):
                        content_text += item.text
            
            content_lower = content_text.lower()
            farewell_phrases = [
                "shubh ho", "शुभ हो", 
                "demo bhej", "डेमो भेज", 
                "keemti samay", "कीमती समय", 
                "great day", "ग्रेट डे",
                "thank you, main aapko whatsapp",
                "aapka din shubh",
                "bhej dunga", "भेज दूंगा",
                "aapka din shubh ho"
            ]
            if any(phrase in content_lower for phrase in farewell_phrases):
                print("--- [FAIL-SAFE] Farewell detected! Calling shutdown NOW ---")
                try:
                    ctx.shutdown()
                except Exception as e:
                    print(f"--- [FAIL-SAFE] Error: {e}")

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
            
            # ✅ Customer ne call uthaya - dashboard mein "On Call" status set karo
            logger.info("Customer answered! Notifying dashboard: on_call")
            asyncio.ensure_future(_notify_dashboard(dashboard_url, lead_id, "on_call"))
            
            # 🎙️ Recording start karo in BACKGROUND (so it doesn't block greeting)
            async def _start_rec_bg():
                eid = await _start_recording(ctx, phone_number, lead_id)
                fnc_ctx.egress_id = eid  # Save to fnc_ctx so we can stop it later
            asyncio.ensure_future(_start_rec_bg())
            
            # Wait for the participant very briefly (max 1 second)
            print("[TRACE] Waiting for participant to appear in Room context...")
            for _ in range(4):
                if any(f"sip_{dial_number}" in p.identity for p in ctx.room.remote_participants.values()):
                    print("[TRACE] Participant fully joined the Room!")
                    break
                await asyncio.sleep(0.25)
            
            # --- CALL END DETECTION ---
            @ctx.room.on("participant_disconnected")
            def on_participant_left(participant):
                if "sip_" in participant.identity:
                    logger.info(f"SIP participant {participant.identity} disconnected - call ended")
                    print(f"--- BOOM: Call ended, participant {participant.identity} left ---")
                    if not getattr(fnc_ctx, 'call_ended_by_tool', False):
                        asyncio.ensure_future(_notify_dashboard(dashboard_url, lead_id, "not_confirmed"))
                    if getattr(fnc_ctx, 'egress_id', None):
                        asyncio.ensure_future(_stop_recording(fnc_ctx.egress_id))
                    async def _delayed_shutdown():
                        await asyncio.sleep(2)
                        ctx.shutdown()
                    asyncio.ensure_future(_delayed_shutdown())
            
            # Let audio track establish extremely fast
            await asyncio.sleep(0.5)
            
            try:
                if hasattr(session, "say"):
                    print(f"[TRACE] Calling session.say() with allow_interruptions=False")
                    # Set allow_interruptions to False so background noise doesn't immediately cut it off!
                    if asyncio.iscoroutinefunction(session.say):
                        await session.say(greeting, allow_interruptions=False)
                    else:
                        session.say(greeting, allow_interruptions=False)
                    print("[TRACE] session.say() executed successfully.")
                else:
                    print("--- BOOM: session.say() method not found on session object ---")
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
