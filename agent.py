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
    google,  # ✅ FIX: Must be imported on main thread to register plugin correctly
)
import openai as openai_client  # ✅ FIX: For explicit Groq client
from livekit.agents import llm
from typing import Annotated, Optional

# Load environment variables
load_dotenv(".env", override=True)

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
    voice_name = config_voice or ""
    
    # List of valid/compatible Sarvam bulbul:v3 voices
    valid_sarvam_voices = [
        "shubh", "ritu", "rahul", "pooja", "simran", "kavya", "amit", 
        "ratan", "rohan", "dev", "ishita", "shreya", "manan", "sumit", 
        "priya", "aditya", "kabir", "neha", "varun", "roopa", "aayan", 
        "ashutosh", "advait", "amelia", "sophia"
    ]

    # Override provider based on voice_name ONLY if provider is NOT explicitly set to cartesia
    if provider != "cartesia":
        if voice_name == "imran" or voice_name == "bdab08ad-4137-4548-b9db-6142854c7525":
            provider = "cartesia"
        elif voice_name in valid_sarvam_voices:
            provider = "sarvam"
        elif voice_name.startswith("aura-"):
            provider = "deepgram"
    elif voice_name in ["anushka", "aravind"]:
        # Fallback incompatible Sarvam voices to supported ones
        provider = "sarvam"
        voice_name = "shreya" if voice_name == "anushka" else "amit"

    print(f"\n==============================================")
    print(f"DEBUG: TTS_PROVIDER resolved is -> {provider}")
    print(f"DEBUG: Voice ID requested is -> {voice_name}")
    print(f"==============================================\n")

    if provider == "cartesia":
        logger.info("Using Cartesia TTS")
        model = os.getenv("CARTESIA_TTS_MODEL", config.CARTESIA_MODEL)
        # Always use configured Hindi voice for Cartesia
        voice_id = config.CARTESIA_VOICE
        language = config.CARTESIA_LANGUAGE
        print(f"DEBUG: Using Cartesia with model={model}, voice={voice_id}, language={language}")
        return cartesia.TTS(model=model, voice=voice_id, language=language)
    
    if provider == "sarvam":
        logger.info(f"Using Sarvam TTS (Voice: {voice_name})")
        model = os.getenv("SARVAM_TTS_MODEL", config.SARVAM_MODEL)
        voice = voice_name if voice_name in valid_sarvam_voices else os.getenv("SARVAM_VOICE", "amit")
        language = os.getenv("SARVAM_LANGUAGE", config.SARVAM_LANGUAGE)
        return sarvam.TTS(model=model, speaker=voice, target_language_code=language)

    if provider == "deepgram":
        voice = voice_name if voice_name.startswith("aura-") else os.getenv("DEEPGRAM_TTS_MODEL", "aura-helios-en")
        logger.info(f"Using Deepgram TTS (Voice: {voice})")
        return deepgram.TTS(model=voice)

    # Default to Deepgram if no matched provider
    voice = voice_name if voice_name.startswith("aura-") else os.getenv("DEEPGRAM_TTS_MODEL", "aura-helios-en")
    logger.info(f"Using Default TTS (Deepgram Voice: {voice})")
    return deepgram.TTS(model=voice)


def _build_llm(config_provider: str = None):
    """Configure the LLM provider based on config or env vars."""
    provider = (config_provider or os.getenv("LLM_PROVIDER", config.DEFAULT_LLM_PROVIDER)).lower()
    
    if provider in ["gemini", "google"]:
        gemini_model = os.getenv("GEMINI_MODEL", config.GEMINI_MODEL)
        print(f"[LLM] Building Gemini LLM with model: {gemini_model}")
        logger.info(f"Using Gemini LLM (model: {gemini_model})")
        # ✅ FIX: Set GOOGLE_API_KEY env var before calling google.LLM()
        os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY", "")
        return google.LLM(
            model=gemini_model,
            temperature=float(os.getenv("GEMINI_TEMPERATURE", str(config.GEMINI_TEMPERATURE))),
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Groq Fallback
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    groq_model = os.getenv("GROQ_MODEL", config.GROQ_MODEL)
    print(f"[LLM] Building Groq LLM with model: {groq_model}")
    logger.info(f"Using Groq LLM (model: {groq_model})")
    
    client = openai_client.AsyncOpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.getenv("GROQ_API_KEY"),
    )
    
    return openai.LLM(
        client=client,
        model=groq_model,
        temperature=float(os.getenv("GROQ_TEMPERATURE", str(config.GROQ_TEMPERATURE))),
    )



class ConversationManager:
    def __init__(self, business_name: str = None):
        self.state = "greeting"
        self.business_name = business_name
        
    def get_system_prompt(self):
        prompt = config.BASE_PROMPT
        if self.business_name:
            prompt += f"\n\n## TARGET BUSINESS DETAILS:\n- You are calling a business named: '{self.business_name}'"
        
        state_instruction = config.STATE_PROMPTS.get(self.state, "")
        prompt += f"\n\n## STATE INSTRUCTIONS:\n{state_instruction}"
        return prompt

class CallStateTools(llm.ToolContext):
    def __init__(self, ctx: agents.JobContext, phone_number: str = None, dashboard_url: str = None, lead_id: str = None, conv_manager: ConversationManager = None):
        super().__init__(tools=[])
        self.ctx = ctx
        self.phone_number = phone_number
        self.dashboard_url = dashboard_url
        self.lead_id = lead_id
        self.conv_manager = conv_manager
        self.session = None  # Will be set after session creation
        self.call_ended_by_tool = False
        self.final_status = None  # ✅ FIX: Hamesha track karo call ka final status
        self.last_user_speech_time = asyncio.get_event_loop().time()

    def trigger_failsafe_hangup(self):
        # ══════════════════════════════════════════════════════════════════
        # TRACE CASE 11: Vobiz Call Disconnect Failsafe
        # Start a 7s failsafe timer. If the call is still active (e.g. because
        # the farewell phrase matching failed or agent got interrupted),
        # we will force ctx.shutdown() to ensure the PSTN call is severed!
        # ══════════════════════════════════════════════════════════════════
        async def _failsafe_shutdown():
            if hasattr(self, 'log_trace'):
                self.log_trace("[TRACE-11 FAILSAFE] ⏰ Failsafe hangup timer started (7s)...")
            else:
                print("--- [TRACE-11 FAILSAFE] ⏰ Failsafe hangup timer started (7s)... ---")
            
            await asyncio.sleep(7)
            
            try:
                if hasattr(self, 'log_trace'):
                    self.log_trace("[TRACE-11 FAILSAFE] 🛑 Failsafe triggered! Ensuring Vobiz call connection is completely cut...")
                else:
                    print("--- [TRACE-11 FAILSAFE] 🛑 Failsafe triggered! Ensuring Vobiz call connection is completely cut... ---")
                
                if getattr(self, 'egress_id', None):
                    try:
                        await _stop_recording(self.egress_id)
                    except Exception as e:
                        print(f"Failsafe recording stop error: {e}")
                
                # Forcibly remove SIP participant to cut Vobiz call
                await _disconnect_sip_call(self.ctx, getattr(self, 'log_trace', None))
                
                self.ctx.shutdown()
                
                if hasattr(self, 'log_trace'):
                    self.log_trace("[TRACE-11 FAILSAFE] ✅ Failsafe ctx.shutdown() completed.")
                else:
                    print("--- [TRACE-11 FAILSAFE] ✅ Failsafe ctx.shutdown() completed. ---")
            except Exception as e:
                print(f"--- [FAILSAFE ERROR] {e} ---")

        asyncio.ensure_future(_failsafe_shutdown())

    def _update_state_prompt(self):
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # FIX: session.chat_ctx.messages.append() causes
        # 'An internal error occurred' in newer LiveKit versions.
        # Use session.update_instructions() instead.
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if not self.session:
            print("[STATE] _update_state_prompt: session not set yet, skipping")
            return
        try:
            new_prompt = self.conv_manager.get_system_prompt()
            # Try modern API first
            if hasattr(self.session, 'update_instructions'):
                self.session.update_instructions(new_prompt)
                print(f"[STATE] Instructions updated via update_instructions(). State: {self.conv_manager.state}")
            elif hasattr(self.session, 'set_instructions'):
                self.session.set_instructions(new_prompt)
                print(f"[STATE] Instructions updated via set_instructions(). State: {self.conv_manager.state}")
            else:
                # Safe fallback: inject via generate_reply context
                print(f"[STATE] update_instructions not available. State tracked internally: {self.conv_manager.state}")
        except Exception as e:
            print(f"[STATE] _update_state_prompt error (non-fatal): {e}")
            logger.warning(f"State prompt update failed: {e}")

    @llm.function_tool(description="Transition to the 'pitch' state. Call this ONLY AFTER: (1) agent has said 'Sir main WebCraft Solutions se baat kar raha hoon. Kya aapke paas ek minute ka samay hai?' AND (2) the customer has REPLIED with 'haan', 'theek hai', 'boliye', 'achha', 'hmm', or any listening/positive word to that question. Do NOT call this immediately after saying the intro line — wait for customer's response first.")
    async def transition_state(self):
        import time
        print(f"[TRACE-STATE] transition_state CALLED at {time.strftime('%H:%M:%S')}")
        logger.info("Transitioning state to PITCH")
        self.conv_manager.state = "pitch"
        self._update_state_prompt()
        print(f"[TRACE-STATE] State is now: {self.conv_manager.state}")
        return ""

    @llm.function_tool(description="Move to the confirmation state. Call this ONLY when the customer EXPLICITLY says they want to see the demo or books a slot.")
    async def initiate_booking_flow(self):
        import time
        print(f"[TRACE-STATE] initiate_booking_flow CALLED at {time.strftime('%H:%M:%S')}")
        
        # ══════════════════════════════════════════════════════════════════
        # TRACE CASE 13: Triple Confirmation Guard
        # Prevent re-entry if already in confirmation_pending or call_ended
        # ══════════════════════════════════════════════════════════════════
        current_state = self.conv_manager.state
        if current_state == "confirmation_pending":
            print(f"--- [TRACE-13 TRIPLE CONFIRM] ⚠️ initiate_booking_flow called AGAIN but already in confirmation_pending! Blocking re-entry. ---")
            if hasattr(self, 'log_trace'):
                self.log_trace(f"[TRACE-13 TRIPLE CONFIRM] ⚠️ BLOCKED: initiate_booking_flow re-called while state='{current_state}'. LLM is looping!")
            return "You have ALREADY asked for confirmation. Do NOT ask again. Wait for customer's yes/no reply."
        if current_state == "call_ended":
            print(f"--- [TRACE-13 TRIPLE CONFIRM] ⚠️ initiate_booking_flow called but call already ended! ---")
            if hasattr(self, 'log_trace'):
                self.log_trace(f"[TRACE-13 TRIPLE CONFIRM] ⚠️ BLOCKED: initiate_booking_flow called after call_ended state.")
            return "Call has already ended. Do not take any more actions. Stay silent."
        
        logger.info("Transitioning to CONFIRMATION_PENDING state")
        self.conv_manager.state = "confirmation_pending"
        self._update_state_prompt()
        print(f"[TRACE-STATE] State is now: {self.conv_manager.state}")
        return "Sir confirm kar raha hoon, kya main demo website ki link WhatsApp par bhej doon?"

    @llm.function_tool(description="""Finalize the booking. Call this ONLY after the customer says YES to your final confirmation question in the confirmation_pending state.
    IMPORTANT: DO NOT ask for WhatsApp number. We already have it. Just call this tool immediately when customer confirms.
    Trigger words: 'haan', 'theek hai', 'bhej do', 'kar do', 'ok', 'yes', 'haan bhej do', 'link bhej do', 'whatsapp kar do', 'send kar do'""")
    async def finalize_demo_booking(self):
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # TRACE CASE 3: Booking confirmation trace
        # Yeh tool tab call hoga jab customer ne confirm kiya
        # Agar yeh log nahi dikh raha aur customer ne confirm bol diya tha
        # toh LLM ne confirmation phrase recognize nahi ki
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        import time
        trace_time = time.strftime("%H:%M:%S")
        
        # ══════════════════════════════════════════════════════════════════
        # TRACE CASE 13: Triple Confirmation Guard
        # Prevent LLM from calling finalize_demo_booking more than once
        # ══════════════════════════════════════════════════════════════════
        finalize_count = getattr(self, '_finalize_call_count', 0) + 1
        self._finalize_call_count = finalize_count
        
        print(f"--- [TRACE-13 TRIPLE CONFIRM] finalize_demo_booking called (attempt #{finalize_count}) at {trace_time} ---")
        if hasattr(self, 'log_trace'):
            self.log_trace(f"[TRACE-13 TRIPLE CONFIRM] finalize_demo_booking attempt #{finalize_count} at {trace_time}")
        
        if finalize_count > 1:
            print(f"--- [TRACE-13 TRIPLE CONFIRM] ⚠️ BLOCKED: finalize_demo_booking already called {finalize_count - 1} time(s) before! LLM is re-invoking! ---")
            if hasattr(self, 'log_trace'):
                self.log_trace(f"[TRACE-13 TRIPLE CONFIRM] ⚠️ BLOCKED: Re-invocation #{finalize_count}. Demo was already confirmed. LLM should stop.")
            return "Demo booking is ALREADY CONFIRMED. Do NOT say anything else. Stay completely silent and wait for the call to end."
        
        print(f"--- [TRACE-3 BOOKING] ✅ finalize_demo_booking CALLED at {trace_time} ---")
        print(f"--- [TRACE-3 BOOKING] Phone: {self.phone_number}, Lead: {self.lead_id} ---")
        print(f"--- [TRACE-3 BOOKING] Dashboard URL: {self.dashboard_url} ---")
        logger.info(f"[TRACE-3] Demo formally confirmed. Phone: {self.phone_number}")
        
        self.call_ended_by_tool = True
        self.final_status = "demo_confirmed"  # ✅ FIX: final status set karo
        self.conv_manager.state = "call_ended"  # ✅ TRACE-13 FIX: Block all further LLM actions
        self._update_state_prompt()  # ✅ Push silence instructions to LLM immediately
        self.trigger_failsafe_hangup()  # ⏰ Start Vobiz hangup failsafe
        wa_number = self.phone_number or ""
        
        if self.dashboard_url and self.lead_id:
            print(f"--- [TRACE-3 BOOKING] Sending PATCH to dashboard: status=demo_confirmed ---")
            try:
                async def _update_demo():
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        url = f"{self.dashboard_url}/api/leads/{self.lead_id}"
                        payload = {"status": "demo_confirmed", "whatsapp_number": wa_number}
                        print(f"--- [TRACE-3 BOOKING] PATCH URL: {url}, Payload: {payload} ---")
                        resp = await client.patch(url, json=payload)
                        print(f"--- [TRACE-3 BOOKING] Dashboard response: {resp.status_code} ---")
                asyncio.ensure_future(_update_demo())
            except Exception as e:
                print(f"--- [TRACE-3 BOOKING] ❌ Dashboard update FAILED: {e} ---")
                logger.error(f"Failed to notify dashboard: {e}")
        else:
            print(f"--- [TRACE-3 BOOKING] ⚠️ Dashboard NOT notified: url={self.dashboard_url}, lead_id={self.lead_id} ---")
        
        # Speak farewell directly and then hang up — don't rely on LLM to re-generate
        farewell = "Thank you sir, aapka demo schedule ho gaya hai. Hamari Team aapko contact karegi. Aapka din shubh ho."
        if self.session and hasattr(self.session, 'say'):
            async def _say_and_hangup():
                try:
                    if asyncio.iscoroutinefunction(self.session.say):
                        await self.session.say(farewell, allow_interruptions=False)
                    else:
                        self.session.say(farewell, allow_interruptions=False)
                    await asyncio.sleep(7.0)  # Let TTS finish speaking the long sentence
                except Exception as e:
                    print(f"[FAREWELL] say() error: {e}")
                    await asyncio.sleep(7.0)
                finally:
                    if getattr(self, 'egress_id', None):
                        await _stop_recording(self.egress_id)
                    await _disconnect_sip_call(self.ctx, getattr(self, 'log_trace', None))
                    self.ctx.shutdown()
            asyncio.ensure_future(_say_and_hangup())
        return ""

    @llm.function_tool(description="End the call. Use this when the customer says they are not interested, already have a website, or just hang up.")
    async def mark_not_interested(self):
        logger.info("Customer not interested.")
        self.call_ended_by_tool = True
        self.final_status = "not_confirmed"  # ✅ FIX: final status set karo
        self.conv_manager.state = "call_ended"  # ✅ TRACE-13 FIX: Block all further LLM actions
        self._update_state_prompt()  # ✅ Push silence instructions to LLM immediately
        self.trigger_failsafe_hangup()  # ⏰ Start Vobiz hangup failsafe
        if self.dashboard_url and self.lead_id:
            try:
                asyncio.ensure_future(_notify_dashboard(self.dashboard_url, self.lead_id, "not_confirmed"))
            except Exception as e:
                pass
        farewell = "Ok sir, koi baat nahi. Apna keemti samay dene ke liye shukriya. Aapka din shubh ho."
        if self.session and hasattr(self.session, 'say'):
            async def _say_and_hangup_ni():
                try:
                    if asyncio.iscoroutinefunction(self.session.say):
                        await self.session.say(farewell, allow_interruptions=False)
                    else:
                        self.session.say(farewell, allow_interruptions=False)
                    await asyncio.sleep(7.0)
                except Exception as e:
                    await asyncio.sleep(7.0)
                finally:
                    if getattr(self, 'egress_id', None):
                        await _stop_recording(self.egress_id)
                    await _disconnect_sip_call(self.ctx, getattr(self, 'log_trace', None))
                    self.ctx.shutdown()
            asyncio.ensure_future(_say_and_hangup_ni())
        return ""

    @llm.function_tool(description="Schedule a callback. Use this when the customer says they are busy, driving, or asks you to call back later/tomorrow.")
    async def request_callback(self, time_preference: Optional[str] = None):
        logger.info(f"Callback requested: {time_preference}")
        self.call_ended_by_tool = True
        self.final_status = "callback_requested"  # ✅ FIX: final status set karo
        self.conv_manager.state = "call_ended"  # ✅ TRACE-13 FIX: Block all further LLM actions
        self._update_state_prompt()  # ✅ Push silence instructions to LLM immediately
        self.trigger_failsafe_hangup()  # ⏰ Start Vobiz hangup failsafe
        if self.dashboard_url and self.lead_id:
            try:
                async def _update_callback():
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        url = f"{self.dashboard_url}/api/leads/{self.lead_id}"
                        payload = {"status": "callback_requested", "notes": f"Callback preference: {time_preference}"}
                        await client.patch(url, json=payload)
                asyncio.ensure_future(_update_callback())
            except Exception as e:
                pass
        farewell = "Theek hai sir, main baad mein call kar lunga. Aapka samay dene ke liye shukriya."
        if self.session and hasattr(self.session, 'say'):
            async def _say_and_hangup_cb():
                try:
                    if asyncio.iscoroutinefunction(self.session.say):
                        await self.session.say(farewell, allow_interruptions=False)
                    else:
                        self.session.say(farewell, allow_interruptions=False)
                    await asyncio.sleep(7.0)
                except Exception as e:
                    await asyncio.sleep(7.0)
                finally:
                    if getattr(self, 'egress_id', None):
                        await _stop_recording(self.egress_id)
                    await _disconnect_sip_call(self.ctx, getattr(self, 'log_trace', None))
                    self.ctx.shutdown()
            asyncio.ensure_future(_say_and_hangup_cb())
        return ""



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


async def _disconnect_sip_call(ctx: agents.JobContext, log_trace_fn=None):
    """Forcibly disconnect any SIP participant to ensure Vobiz hangs up."""
    try:
        sip_identities = [p.identity for p in ctx.room.remote_participants.values() if "sip_" in p.identity]
        if log_trace_fn:
            log_trace_fn(f"[TRACE-15 VOBIZ DISCONNECT] Found SIP participants in room: {sip_identities}")
        else:
            print(f"[TRACE-15 VOBIZ DISCONNECT] Found SIP participants in room: {sip_identities}")
        
        if not sip_identities:
            if log_trace_fn:
                log_trace_fn("[TRACE-15 VOBIZ DISCONNECT] No active SIP participants found to disconnect.")
            return

        for identity in sip_identities:
            if log_trace_fn:
                log_trace_fn(f"[TRACE-15 VOBIZ DISCONNECT] Requesting removal of participant '{identity}'...")
            await ctx.api.room.remove_participant(
                api.RoomParticipantIdentity(
                    room=ctx.room.name,
                    identity=identity
                )
            )
            if log_trace_fn:
                log_trace_fn(f"[TRACE-15 VOBIZ DISCONNECT] ✅ Successfully removed participant '{identity}'")
    except Exception as e:
        if log_trace_fn:
            log_trace_fn(f"[TRACE-15 VOBIZ DISCONNECT] ❌ Error removing participant: {e}")
        else:
            print(f"[TRACE-15 VOBIZ DISCONNECT] ❌ Error removing participant: {e}")


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
    dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:3000")
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

    # Initialize function context and Conversation Manager
    conv_manager = ConversationManager(business_name)
    fnc_ctx = CallStateTools(ctx, phone_number, dashboard_url, lead_id, conv_manager)

    # Resilient configuration fetching (ignoring metadata overrides, reading directly from config.py and .env)
    m_provider = os.getenv("LLM_PROVIDER", config.DEFAULT_LLM_PROVIDER)
    tts_provider = os.getenv("TTS_PROVIDER", config.DEFAULT_TTS_PROVIDER)
    m_voice = None  # Resolved inside _build_tts based on provider settings
    
    print(f"--- BOOM: Initializing with LLM Provider: {m_provider}, TTS Provider: {tts_provider} ---")

    # Initialize the Agent Session with optimized settings
    try:
        session = AgentSession(
            vad=silero.VAD.load(
                min_silence_duration=0.35,  # Lower = faster turn-end detection = less latency
                min_speech_duration=0.15    # Slightly lower to catch short replies faster
            ),
            stt=deepgram.STT(
                model=config.STT_MODEL, 
                language=config.STT_LANGUAGE, 
                interim_results=True
            ), 
            llm=_build_llm(m_provider),
            tts=_build_tts(tts_provider, m_voice),
        )
        print("--- BOOM: Session Object Created ---")
    except Exception as e:
        print(f"--- BOOM CRITICAL ERROR: Session Init Failed: {e} ---")
        # Extreme fallback without OpenAI defaults
        session = AgentSession(
            vad=silero.VAD.load(min_silence_duration=0.5),
            stt=deepgram.STT(model="nova-2", language="hi"),
            llm=_build_llm(m_provider),
            tts=deepgram.TTS(model=config.DEFAULT_TTS_VOICE),
        )

    # Build greeting using config — inject business name dynamically
    if business_name:
        greeting = config.INITIAL_GREETING.format(business_name=business_name)
    else:
        greeting = config.INITIAL_GREETING_FALLBACK

    # Build dynamic instructions using state manager
    system_prompt = conv_manager.get_system_prompt()

    # Start the session
    print("--- BOOM: Starting Session ---")
    await session.start(
        room=ctx.room,
        agent=OutboundAssistant(tools=list(fnc_ctx.function_tools.values()), instructions=system_prompt),
    )
    fnc_ctx.session = session  # Inject session so tools can update state dynamically
    print("--- BOOM: Session Started Successfully ---")

    # --- TIMEOUT LOGIC (Silence Detection) ---
    _stop_monitor = asyncio.Event()

    async def _timeout_monitor():
        try:
            # Give 15s leeway for call setup
            await asyncio.sleep(15)
            already_prompted = False
            while not fnc_ctx.call_ended_by_tool and not _stop_monitor.is_set():
                current_time = asyncio.get_event_loop().time()
                silence_duration = current_time - fnc_ctx.last_user_speech_time

                if silence_duration > 30:
                    print("--- [TRACE-5 SILENCE] 30s silence. Dropping call silently. ---")
                    fnc_ctx.call_ended_by_tool = True
                    _stop_monitor.set()
                    break
                elif silence_duration > 18 and not already_prompted:
                    already_prompted = True
                    print("--- [TRACE-5 SILENCE] 18s silence. No fallback speech. ---")

                if fnc_ctx.last_user_speech_time > current_time - 5:
                    already_prompted = False

                # ✅ Simple sleep — cancels cleanly via CancelledError
                await asyncio.sleep(2)

        except asyncio.CancelledError:
            # ✅ Task cancelled cleanly — no 'destroyed but pending' warning
            print("[CLEANUP] _timeout_monitor cancelled cleanly.")

    # ✅ Store reference + named task
    _timeout_task = asyncio.create_task(_timeout_monitor())
    _timeout_task.set_name("timeout_monitor")

    # ✅ Cancel task via ctx shutdown callback (more reliable than session.on("close"))
    async def _cancel_timeout_task():
        _stop_monitor.set()
        if not _timeout_task.done():
            _timeout_task.cancel()
            try:
                await _timeout_task
            except asyncio.CancelledError:
                pass

    ctx.add_shutdown_callback(_cancel_timeout_task)

    import time

    def _log_trace(msg_text):
        try:
            ts = time.strftime("%H:%M:%S")
            line = f"[{ts}] {msg_text}"
            with open("live_debug.txt", "a", encoding="utf-8") as f:
                f.write(line + "\n")
            print(line)  # Also print to console for real-time visibility
        except:
            pass

    fnc_ctx.log_trace = _log_trace

    # ══════════════════════════════════════════════════════════════════
    # COMPATIBILITY SHIM FOR OLDER LIVEKIT CHAT_CTX API
    # ══════════════════════════════════════════════════════════════════
    class ChatCtxCompat:
        def __init__(self, history):
            self._history = history
        @property
        def messages(self):
            class MessageListCompat(list):
                def __init__(self, history):
                    super().__init__(history.messages())
                    self._history = history
                def append(self, msg):
                    kwargs = {"role": msg.role, "content": msg.content}
                    for attr in ["id", "interrupted", "created_at", "metrics", "extra"]:
                        if hasattr(msg, attr):
                            val = getattr(msg, attr)
                            if val is not None:
                                kwargs[attr] = val
                    self._history.add_message(**kwargs)
            return MessageListCompat(self._history)

    session.chat_ctx = ChatCtxCompat(session.history)
    _log_trace("[TRACE-SYSTEM] Compatibility shim injected: session.chat_ctx is mapped to session.history.")

    # ══════════════════════════════════════════════════════════════════
    # TRACE DETAILS & MONITOR VARIABLES
    # ══════════════════════════════════════════════════════════════════
    _latency_tracker = {"user_speech_end": None, "llm_start": None}
    _CONFIRMATION_KEYWORDS = [
        "thik hai", "ठीक है", "theek hai", "haan bhej", "हाँ भेज", "bhej do",
        "kar do", "whatsapp kar do", "link bhej", "send kar do", "ok bhej",
        "haan kar do", "yes kar do", "bej do", "bhejdo", "yes send",
        "confirm", "book kar", "schedule kar", "interested", "chahiye"
    ]

    # Helper function to extract plain text content from ChatMessage
    def _get_msg_text(msg) -> str:
        content_text = ""
        if isinstance(msg.content, str):
            content_text = msg.content
        elif isinstance(msg.content, list):
            for item in msg.content:
                if isinstance(item, str):
                    content_text += item
                elif hasattr(item, 'text'):
                    content_text += item.text
        return content_text

    # ══════════════════════════════════════════════════════════════════
    # CONSOLIDATED SPEECH EVENT HANDLERS
    # ══════════════════════════════════════════════════════════════════
    def on_user_speech(msg: llm.ChatMessage):
        fnc_ctx.last_user_speech_time = asyncio.get_event_loop().time()
        content_str = _get_msg_text(msg)
        if not content_str:
            return
            
        logger.info(f"USER: {content_str}")
        print(f"\n--- BOOM USER SAID: {content_str} ---")
        
        # Write to log files
        with open("chat_debug.txt", "a", encoding="utf-8") as f:
            f.write(f"USER: {content_str}\n")
        with open("call_logs.jsonl", "a", encoding="utf-8") as log_file:
            log_file.write(json.dumps({"type": "user_speech", "content": content_str, "state": conv_manager.state}) + "\n")

        # TRACE CASE 2 & 7: User speech ended
        _latency_tracker["user_speech_end"] = time.time()
        _log_trace(f"[TRACE-2 LATENCY] User speech committed at {time.strftime('%H:%M:%S')} — LLM processing starting... Text: '{content_str}'")
        
        if getattr(fnc_ctx, 'greeting_played', False) and not getattr(fnc_ctx, 'first_user_speech_received', False):
            fnc_ctx.first_user_speech_received = True
            _log_trace(f"[TRACE-7 GREETING SILENCE] 🎤 User answered greeting! STT heard: '{content_str}'")
            _log_trace(f"[TRACE-7 GREETING SILENCE] Waiting for LLM (Gemini/Groq) to generate reply...")

        # TRACE CASE 3: Confirmation Phrase Detection
        content_lower = content_str.lower()
        state = conv_manager.state
        _log_trace(f"[TRACE-3 CONFIRM] User said: '{content_str}' | State: {state}")
        matched_keywords = [kw for kw in _CONFIRMATION_KEYWORDS if kw in content_lower]
        if matched_keywords:
            _log_trace(f"[TRACE-3 CONFIRM] ✅ Confirmation keywords detected: {matched_keywords}")
            if state == "confirmation_pending":
                _log_trace(f"[TRACE-3 CONFIRM] State=confirmation_pending + keywords matched → finalize_demo_booking SHOULD be called")
                _log_trace(f"[TRACE-3 CONFIRM] If tool NOT called in next 3s, LLM failed to recognize confirmation")
            else:
                _log_trace(f"[TRACE-3 CONFIRM] ⚠️  State is '{state}', not 'confirmation_pending' — initiate_booking_flow needed first")

    def on_agent_speech(msg: llm.ChatMessage):
        content_str = _get_msg_text(msg)
        if not content_str:
            return
            
        logger.info(f"AGENT: {content_str}")
        print(f"--- BOOM AGENT SAID: {content_str} ---\n")
        
        # Write to log files
        with open("chat_debug.txt", "a", encoding="utf-8") as f:
            f.write(f"AGENT: {content_str}\n")
        with open("call_logs.jsonl", "a", encoding="utf-8") as log_file:
            log_file.write(json.dumps({"type": "agent_speech", "content": content_str, "state": conv_manager.state}) + "\n")

        content_lower = content_str.lower()

        # TRACE CASE 2 & 7: Agent speech committed latency tracker
        if _latency_tracker["user_speech_end"]:
            latency = time.time() - _latency_tracker["user_speech_end"]
            _log_trace(f"[TRACE-2 LATENCY] Agent speech committed at {time.strftime('%H:%M:%S')} — E2E Latency: {latency:.2f}s")
            if latency > 3.0:
                _log_trace(f"[TRACE-2 LATENCY] ⚠️  SLOW RESPONSE ({latency:.2f}s)! Possible causes:")
                _log_trace(f"[TRACE-2 LATENCY]   → Groq/Gemini API latency (check LLM_PROVIDER={os.getenv('LLM_PROVIDER', 'not set')})")
                _log_trace(f"[TRACE-2 LATENCY]   → Tool call overhead (LLM deciding which tool to call)")
                _log_trace(f"[TRACE-2 LATENCY]   → TTS generation delay (provider: {os.getenv('TTS_PROVIDER', 'not set')})")
            _latency_tracker["user_speech_end"] = None
            
        if getattr(fnc_ctx, 'first_user_speech_received', False) and not getattr(fnc_ctx, 'first_agent_reply_received', False):
            fnc_ctx.first_agent_reply_received = True
            _log_trace(f"[TRACE-7 GREETING SILENCE] 🤖 Agent replied successfully after greeting!")

        # TRACE CASE 6: Double Introduction Trace
        if "nitin" in content_lower or "webcraft" in content_lower:
            if getattr(fnc_ctx, 'has_introduced_once', False):
                _log_trace(f"[TRACE-6 INTRO] ⚠️  DOUBLE INTRO DETECTED! Agent re-introduced itself: {content_str}")
                _log_trace(f"[TRACE-6 INTRO] FIX: Ensure LLM prompt strictly forbids repeating the name.")
            else:
                fnc_ctx.has_introduced_once = True
                _log_trace(f"[TRACE-6 INTRO] Agent introduced itself successfully (First Time).")

        # TRACE CASE 13: Triple Confirmation (Speaking after call ended)
        if conv_manager.state == "call_ended":
            _log_trace(f"[TRACE-13 TRIPLE CONFIRM] 🚨 AGENT SPOKE AFTER CALL ENDED! State=call_ended but agent said: '{content_str[:100]}'")
            _log_trace(f"[TRACE-13 TRIPLE CONFIRM] → This is the triple confirmation bug. LLM is ignoring call_ended instructions.")

        # TRACE CASE 14: Intro Phrase Repetition Detection
        _repeat_keywords = ["webcraft solutions", "1 minute", "ek minute"]
        if any(kw in content_lower for kw in _repeat_keywords):
            repeat_count = getattr(fnc_ctx, '_intro_repeat_count', 0) + 1
            fnc_ctx._intro_repeat_count = repeat_count
            _log_trace(f"[TRACE-14 INTRO REPEAT] Count #{repeat_count} | State: {conv_manager.state} | Said: '{content_str[:80]}'")
            if repeat_count >= 2:
                _log_trace(f"[TRACE-14 INTRO REPEAT] ⚠️ REPEATED! Agent said intro phrase {repeat_count} times!")
                _log_trace(f"[TRACE-14 INTRO REPEAT] Root causes:")
                _log_trace(f"[TRACE-14 INTRO REPEAT]   → LLM is stuck in GREETING state and not transitioning to PITCH")
                _log_trace(f"[TRACE-14 INTRO REPEAT]   → transition_state tool was NOT called by LLM")

        # TRACE-9 LATENCY BREAKDOWN (from metadata)
        if hasattr(msg, "metrics") and msg.metrics:
            m = msg.metrics
            e2e = m.get("e2e_latency", 0)
            llm_ttft = m.get("llm_node_ttft", 0)
            tts_ttfb = m.get("tts_node_ttfb", 0)
            print(f"--- [TRACE-9 LATENCY BREAKDOWN] E2E: {e2e:.2f}s | LLM TTFT: {llm_ttft:.2f}s | TTS TTFB: {tts_ttfb:.2f}s ---")
            logger.info(f"[TRACE-9 LATENCY] E2E: {e2e:.2f}s, LLM: {llm_ttft:.2f}s, TTS: {tts_ttfb:.2f}s")

        # TRACE CASE 4 & 8: Farewell & Call Disconnect Trace
        _log_trace(f"[TRACE-4 FAREWELL] Agent said: '{content_str[:100]}...' | call_ended_by_tool={fnc_ctx.call_ended_by_tool}")
        farewell_phrases = [
            "shubh ho", "शुभ ho", 
            "shukriya", "शुक्रिया",
            "team aapko contact karegi",
            "great day", "ग्रेट डे",
            "aapka din shubh",
            "call kar lunga",
            "din shubh",        # "aapka din shubh ho"
            "dhanyawad",        # "dhanyawad"
            "धन्यवाद",          # Hindi dhanyawad
            "thank you",        # finalize_demo_booking return karta hai yeh
            "have a great",     # finalize return phrase
            "baad me call",     # callback phrase
            "samay dene",       # not_interested phrase
            "keemti samay",     # not_interested phrase
            "kal connect",      # demo confirmed phrase
            "schedule ho gaya", # demo confirmed phrase
        ]
        matched_phrase = [p for p in farewell_phrases if p in content_lower]
        _log_trace(f"[TRACE-4 FAREWELL] Farewell phrases matched: {matched_phrase}")
        
        if matched_phrase and not fnc_ctx.call_ended_by_tool:
            _log_trace(f"[TRACE-4 FAREWELL] ⚠️  FAREWELL DETECTED but call_ended_by_tool=False!")
            _log_trace(f"[TRACE-4 FAREWELL]   → Tool (finalize/not_interested/callback) was NOT called before farewell")
            _log_trace(f"[TRACE-4 FAREWELL]   → This is why disconnect is NOT happening")
        elif matched_phrase and fnc_ctx.call_ended_by_tool:
            _log_trace(f"[TRACE-4 FAREWELL] ✅ Farewell + call_ended_by_tool=True → disconnect will trigger in 4s")
        elif not matched_phrase and fnc_ctx.call_ended_by_tool:
            _log_trace(f"[TRACE-4 FAREWELL] ⚠️  call_ended_by_tool=True but NO farewell phrase matched!")

        print(f"--- [TRACE-8 FAREWELL HANGUP] call_ended_by_tool={fnc_ctx.call_ended_by_tool}, matched={matched_phrase}, text='{content_str[:30]}...' ---")
        
        # Only terminate if a tool ended the call AND a farewell phrase was spoken
        if fnc_ctx.call_ended_by_tool and matched_phrase:
            print(f"--- [TRACE-8 FAREWELL HANGUP] ✅ Farewell detected! Waiting 4s for TTS to flush... ---")
            
            async def _graceful_shutdown():
                print("--- [TRACE-8 FAREWELL HANGUP] Sleep started... ---")
                _log_trace(f"[TRACE-10 VOBIZ HANGUP] Graceful hangup initiated. Waiting 2s for TTS flush...")
                await asyncio.sleep(1.5)
                print("--- [TRACE-8 FAREWELL HANGUP] Sleep ended. Shutting down room now... ---")
                _log_trace(f"[TRACE-10 VOBIZ HANGUP] 🛑 Triggering Vobiz disconnect logic...")
                if getattr(fnc_ctx, 'egress_id', None):
                    await _stop_recording(fnc_ctx.egress_id)
                
                # Forcibly remove SIP participant to cut Vobiz call
                await _disconnect_sip_call(ctx, _log_trace)
                
                ctx.shutdown()
                _log_trace(f"[TRACE-10 VOBIZ HANGUP] ✅ ctx.shutdown() completed. Agent has hung up the call.")
            
            asyncio.ensure_future(_graceful_shutdown())

    # ══════════════════════════════════════════════════════════════════
    # NATIVE LIVEKIT EVENT LISTENERS
    # ══════════════════════════════════════════════════════════════════
    @session.on("conversation_item_added")
    def on_conversation_item_added_dispatch(ev):
        _log_trace(f"[TRACE-LIVEKIT] 📝 conversation_item_added: {ev}")
        item = ev.item
        if not hasattr(item, "role"):
            return
        if item.role == "user":
            on_user_speech(item)
        elif item.role == "assistant":
            on_agent_speech(item)

    @session.on("agent_state_changed")
    def on_agent_state_changed(ev):
        _log_trace(f"[TRACE-LIVEKIT] 🤖 Agent State Changed: {ev.old_state} -> {ev.new_state}")
        if ev.new_state == "speaking":
            _log_trace(f"[TRACE-TTS] 🎙️ TTS Playout Started (Agent is speaking).")
        elif ev.new_state == "thinking":
            _log_trace(f"[TRACE-LLM] 🧠 LLM Generation Started (Agent is thinking). LLM Provider: {os.getenv('LLM_PROVIDER', 'not set')}")

    @session.on("user_state_changed")
    def on_user_state_changed(ev):
        _log_trace(f"[TRACE-LIVEKIT] 👤 User State Changed: {ev.old_state} -> {ev.new_state}")

    @session.on("speech_created")
    def on_speech_created(ev):
        _log_trace(f"[TRACE-TTS] 🎙️ Speech Created (Source: '{ev.source}', User-initiated: {ev.user_initiated})")
        _log_trace(f"[TRACE-TTS] Configured TTS Provider: {os.getenv('TTS_PROVIDER', 'not set')}, Voice: {config.DEFAULT_TTS_VOICE}")

    @session.on("user_input_transcribed")
    def on_user_input_trace(ev):
        _log_trace(f"[TRACE-STT] 🎤 User Input Transcribed: '{ev.transcript}' (is_final={ev.is_final}, confidence={getattr(ev, 'confidence', 'N/A')})")

    @session.on("function_tools_executed")
    def on_function_tools_trace_1(ev):
        ev_str = str(ev)
        _log_trace(f"[TRACE-1 WHATSAPP] function_tools_executed: {ev_str}")
        if "whatsapp" in ev_str.lower():
            _log_trace(f"[TRACE-1 WHATSAPP] ⚠️  WHATSAPP NUMBER BEING REQUESTED! Tool args: {ev_str}")
            _log_trace(f"[TRACE-1 WHATSAPP] Current conv state: {conv_manager.state}")
            _log_trace(f"[TRACE-1 WHATSAPP] FIX: finalize_demo_booking should NOT take whatsapp_number param")

        if "finalize_demo_booking" in ev_str:
            _log_trace(f"[TRACE-3 CONFIRM] ✅ finalize_demo_booking WAS called! Dashboard update should happen.")
        elif "initiate_booking_flow" in ev_str:
            _log_trace(f"[TRACE-3 CONFIRM] initiate_booking_flow called — state moving to confirmation_pending")
        elif "mark_not_interested" in ev_str or "request_callback" in ev_str:
            _log_trace(f"[TRACE-3 CONFIRM] ⚠️  Wrong tool called instead of finalize: {ev_str}")

    @session.on("error")
    def on_session_error(err):
        _log_trace(f"[TRACE ERROR]: type='error' error={err}")
        _log_trace(f"[TRACE ERROR-DETAILS] Source: {getattr(err, 'source', 'N/A')}, Error: {getattr(err, 'error', 'N/A')}")
        _log_trace(f"[TRACE-7 GREETING SILENCE] ❌ A fatal error occurred that might have stopped the agent from replying: {err}")

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
        
        # ══════════════════════════════════════════════════════════════════
        # TRACE CASE 14: SIP Outbound Dialing Trace
        # ══════════════════════════════════════════════════════════════════
        _log_trace(f"[TRACE-14 SIP DIAL] Dialing {dial_number} on trunk {config.SIP_TRUNK_ID}...")
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

            # ✅ FIX: Timer reset karo — abhi customer ne call uthaya hai
            # Pehle last_user_speech_time agent init pe set tha (bahut pehle)
            # Isse silence timer prematurely fire ho jaata tha
            fnc_ctx.last_user_speech_time = asyncio.get_event_loop().time()
            print("[TRACE] Silence timer RESET on call answer.")

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
                    _log_trace(f"[TRACE-10 VOBIZ HANGUP] 🚪 SIP Participant '{participant.identity}' disconnected from Room. Vobiz PSTN call severed!")

                    # ✅ FIX: Hamesha dashboard update karo — chahe tool chala ho ya na chala ho
                    # final_status tool ne set kiya hoga, warna default "not_confirmed" (customer ne call kaata)
                    resolved_status = getattr(fnc_ctx, 'final_status', None) or "not_confirmed"
                    _log_trace(f"[TRACE-10 VOBIZ HANGUP] 📊 Final call outcome resolved: '{resolved_status}'. Updating dashboard...")
                    asyncio.ensure_future(_notify_dashboard(dashboard_url, lead_id, resolved_status))

                    if getattr(fnc_ctx, 'egress_id', None):
                        asyncio.ensure_future(_stop_recording(fnc_ctx.egress_id))
                    async def _delayed_shutdown():
                        await asyncio.sleep(2)
                        _log_trace(f"[TRACE-10 VOBIZ HANGUP] 🛑 Severing remaining agent connection via ctx.shutdown()...")
                        ctx.shutdown()
                        _log_trace(f"[TRACE-10 VOBIZ HANGUP] ✅ Call lifecycle completely ended.")
                    asyncio.ensure_future(_delayed_shutdown())
            
            # No extra sleep needed — participant join loop above already handled timing
            
            try:
                if hasattr(session, "say"):
                    print(f"[TRACE] Calling session.say() with allow_interruptions=True")
                    if asyncio.iscoroutinefunction(session.say):
                        await session.say(greeting, allow_interruptions=True)
                    else:
                        session.say(greeting, allow_interruptions=True)

                    _log_trace(f"[TRACE-7 GREETING SILENCE] ✅ Greeting played via session.say(). Agent is now listening for User...")
                    fnc_ctx.greeting_played = True

                    # ══════════════════════════════════════════════════════════════════
                    # TRACE CASE 12: Initial Greeting Injection Trace
                    # Append the spoken greeting to chat_ctx.messages so the LLM is
                    # aware of what was already said, preventing a double introduction.
                    # ══════════════════════════════════════════════════════════════════
                    _log_trace(f"[TRACE-12 GREETING INJECTION] 📝 Appending initial greeting to chat context to prevent double introduction: '{greeting}'")
                    session.chat_ctx.messages.append(
                        llm.ChatMessage(
                            role="assistant",
                            content=greeting
                        )
                    )

                    # ✅ FIX: Greeting khatam hone ke baad timer phir reset karo
                    # Yahi woh moment hai jab customer ko respond karna hai
                    # Ab se hi 18s ka silence window shuru hoga
                    fnc_ctx.last_user_speech_time = asyncio.get_event_loop().time()
                    print("[TRACE-7 GREETING SILENCE] Greeting done. Silence timer RESET. Waiting for customer response...")
                else:
                    print("--- BOOM: session.say() method not found on session object ---")
            except Exception as e:
                import traceback
                print(f"--- BOOM ERROR IN GREETING: {e} ---")
                traceback.print_exc()
            
            print("--- BOOM: Greet logic finished ---")
            
        except Exception as e:
            logger.error(f"Failed to place outbound call: {e}")
            _log_trace(f"[TRACE-14 SIP DIAL] 🚨 Failed to place outbound call! Error: {e}")
            # Call failed - update status to no_answer
            await _notify_dashboard(dashboard_url, lead_id, "no_answer")
            ctx.shutdown()
    else:
        # Fallback for inbound calls (if this agent is used for that) OR Dashboard calls where user is already there
        logger.info("Detecting if we should greet...")
        if asyncio.iscoroutinefunction(session.generate_reply):
            await session.generate_reply(instructions=config.FALLBACK_GREETING)
        else:
            session.generate_reply(instructions=config.FALLBACK_GREETING)


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
