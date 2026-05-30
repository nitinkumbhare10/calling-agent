import os
import time
import logging
import json
from collections import deque
from datetime import datetime
from dotenv import load_dotenv
from openai import AsyncOpenAI, RateLimitError, APIStatusError

# Configure logging format with timestamp
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

STATE_FILE = "groq_rotator_state.json"

class AllKeysExhaustedException(Exception):
    """Raised when all available Groq API keys are exhausted for the day."""
    pass

class GroqKeyInfo:
    """Wrapper to hold Groq client state and usage tracking metrics using OpenAI SDK."""
    def __init__(self, name: str, key_value: str):
        self.name = name
        self.key_value = key_value
        self.last_used_timestamp = 0.0
        self.daily_tokens_used = 0
        self.exhausted = False
        # Pre-instantiate AsyncOpenAI client pointing to Groq API endpoint
        self.client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=key_value
        )

class GroqRotator:
    """Manages circular rotation, rate limits, and daily token quotas for Groq API keys with cross-process persistence."""
    def __init__(self, daily_limit: int = 450000, reuse_delay: float = 60.0):
        self.daily_limit = daily_limit
        self.reuse_delay = reuse_delay
        self.current_key = None
        self.last_reset_date = datetime.now().date()
        
        # Load environment variables
        load_dotenv()
        
        # Gather keys matching GROQ_KEY_1 to GROQ_KEY_10 uniquely
        keys = []
        seen_values = set()
        
        def add_key_if_unique(name, value):
            if value and value not in seen_values:
                keys.append(GroqKeyInfo(name, value))
                seen_values.add(value)
                
        # 1. Load numbered GROQ_KEY_1 to GROQ_KEY_10 first
        for i in range(1, 11):
            add_key_if_unique(f"GROQ_KEY_{i}", os.getenv(f"GROQ_KEY_{i}"))
            
        # 2. Load primary/fallback GROQ_API_KEY as backup
        add_key_if_unique("GROQ_API_KEY", os.getenv("GROQ_API_KEY"))
        
        self.keys_queue = deque(keys)
        
        # Load persisted state to handle multi-process runs
        self.load_state()
        logging.info(f"GroqRotator initialized with {len(self.keys_queue)} unique keys.")

    def load_state(self):
        """Loads usage state and last used key from file for cross-process state persistence."""
        if not self.keys_queue:
            return
            
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    state = json.load(f)
                
                # Check if we need to reset daily tokens (if day has changed since last reset)
                last_reset_str = state.get("last_reset_date", "")
                today_str = str(datetime.now().date())
                
                if last_reset_str and last_reset_str != today_str:
                    logging.info("New day detected during state load. Resetting daily token counts.")
                    state["daily_usage"] = {}
                    state["last_reset_date"] = today_str
                
                # Apply daily usage and exhaustion status to keys
                daily_usage = state.get("daily_usage", {})
                for key_info in self.keys_queue:
                    key_state = daily_usage.get(key_info.name, {})
                    key_info.daily_tokens_used = key_state.get("daily_tokens_used", 0)
                    key_info.exhausted = key_state.get("exhausted", False)
                    key_info.last_used_timestamp = key_state.get("last_used_timestamp", 0.0)
                    
                self.last_reset_date = datetime.strptime(state.get("last_reset_date", today_str), "%Y-%m-%d").date()
                
                # Rotate queue to position the next key after last_used_key_name at the front
                last_used = state.get("last_used_key_name", "")
                if last_used:
                    names = [k.name for k in self.keys_queue]
                    if last_used in names:
                        idx = names.index(last_used)
                        # Rotate the queue so that index + 1 is at the front
                        self.keys_queue.rotate(-(idx + 1))
                        logging.info(f"Resumed rotation state. Last used: {last_used}. Next in queue: {self.keys_queue[0].name}")
            except Exception as e:
                logging.error(f"Failed to load rotator state from file: {e}")
                self.last_reset_date = datetime.now().date()
        else:
            self.last_reset_date = datetime.now().date()
            self.save_state()

    def save_state(self):
        """Saves current usage state and last used key to file."""
        if not self.keys_queue:
            return
            
        try:
            daily_usage = {}
            for key_info in self.keys_queue:
                daily_usage[key_info.name] = {
                    "daily_tokens_used": key_info.daily_tokens_used,
                    "exhausted": key_info.exhausted,
                    "last_used_timestamp": key_info.last_used_timestamp
                }
            
            state = {
                "last_used_key_name": self.current_key.name if self.current_key else "",
                "daily_usage": daily_usage,
                "last_reset_date": str(self.last_reset_date)
            }
            
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=4)
        except Exception as e:
            logging.error(f"Failed to save rotator state to file: {e}")

    def get_next_key(self) -> AsyncOpenAI:
        """Returns the next available OpenAI client pointing to Groq after verifying reuse delay and token quotas."""
        # Reload state to get latest values from other processes
        self.load_state()
            
        if not self.keys_queue:
            raise AllKeysExhaustedException("No API keys loaded in GroqRotator.")
            
        attempts = 0
        num_keys = len(self.keys_queue)
        
        while attempts < num_keys:
            key_info = self.keys_queue[0]
            
            # Check if key has already hit daily limit
            if key_info.exhausted or key_info.daily_tokens_used >= self.daily_limit:
                key_info.exhausted = True
                logging.info(f"Skipping key {key_info.name} - daily token limit exceeded.")
                self.keys_queue.rotate(-1)
                attempts += 1
                continue
                
            # Check reuse delay constraint
            now = time.time()
            elapsed = now - key_info.last_used_timestamp
            if key_info.last_used_timestamp > 0 and elapsed < self.reuse_delay:
                wait_time = self.reuse_delay - elapsed
                logging.info(f"Key {key_info.name} reuse delay not met (last used {elapsed:.1f}s ago). Sleeping for {wait_time:.2f}s...")
                time.sleep(wait_time)
                
            # Valid key found: update timestamp, set as current, and rotate queue for next call
            key_info.last_used_timestamp = time.time()
            self.current_key = key_info
            self.keys_queue.rotate(-1)
            
            logging.info(f"Selected active key: {key_info.name}")
            
            # Persist state before returning client
            self.save_state()
            return key_info.client
            
        raise AllKeysExhaustedException("All Groq API keys are exhausted for the day.")

    def report_usage(self, tokens_used: int):
        """Updates the token count for the active key."""
        # Reload state to get latest token count from other processes
        self.load_state()
        
        if self.current_key:
            # Re-fetch our current key status to be accurate
            for k in self.keys_queue:
                if k.name == self.current_key.name:
                    k.daily_tokens_used += tokens_used
                    logging.info(
                        f"Usage reported on {k.name}: +{tokens_used} tokens. "
                        f"Total today: {k.daily_tokens_used}/{self.daily_limit} tokens."
                    )
                    if k.daily_tokens_used >= self.daily_limit:
                        k.exhausted = True
                        logging.warning(f"Key {k.name} has hit the daily limit threshold.")
                    break
            self.save_state()

    def handle_error(self, error: Exception):
        """Decides whether to rotate keys on rate limit/exhaustion or raise the exception."""
        # Reload state first
        self.load_state()
        
        if isinstance(error, RateLimitError):
            err_msg = str(error).lower()
            if "quota" in err_msg or "daily" in err_msg or "limit exceeded" in err_msg:
                if self.current_key:
                    logging.warning(f"Daily quota limit hit for {self.current_key.name} via API error. Marking exhausted.")
                    # Mark exhausted on queue item
                    for k in self.keys_queue:
                        if k.name == self.current_key.name:
                            k.exhausted = True
            else:
                if self.current_key:
                    logging.warning(f"Rate limit (429) hit for {self.current_key.name}. Rotating to next key.")
            self.save_state()
            return  # Allow rotation and retry without raising
            
        elif isinstance(error, APIStatusError) and error.status_code == 403:
            if self.current_key:
                logging.warning(f"Authentication/Authorization error (403) for key {self.current_key.name}. Marking exhausted.")
                for k in self.keys_queue:
                    if k.name == self.current_key.name:
                        k.exhausted = True
            self.save_state()
            return  # Allow rotation and retry without raising
            
        else:
            logging.error(f"Unhandleable error encountered: {error}")
            raise error

    def reset_daily(self):
        """Resets all token counts and exhaustion states."""
        logging.info("Resetting daily token counts and exhaustion states for all keys.")
        for key_info in self.keys_queue:
            key_info.daily_tokens_used = 0
            key_info.exhausted = False
        self.last_reset_date = datetime.now().date()
        self.save_state()

# Global singleton instance for the worker process
rotator = GroqRotator()

# --- SIMULATED TEST BLOCK ---
if __name__ == "__main__":
    from unittest.mock import MagicMock
    
    print("\n==================================================")
    print("RUNNING GROQ KEY ROTATOR DEMONSTRATION")
    print("==================================================\n")
    
    # Pre-populate dummy keys in environment for verification
    for i in range(1, 11):
        if not os.getenv(f"GROQ_KEY_{i}"):
            os.environ[f"GROQ_KEY_{i}"] = f"gsk_mock_api_key_value_for_rotation_{i}"
            
    # Reset file state for fresh test run
    if os.path.exists(STATE_FILE):
        try:
            os.remove(STATE_FILE)
        except:
            pass
            
    # Initialize rotator. 
    # For testing, we use a 1.0s reuse delay and a 10,000 daily token limit per key
    test_rotator = GroqRotator(daily_limit=10000, reuse_delay=1.0)
    
    # Mock each client's API call behavior to demonstrate different rotation states
    mock_responses = [
        # Call 1-5: Normal execution (1500 tokens per call)
        {"tokens": 1500, "raise_rate_limit": False},
        {"tokens": 1500, "raise_rate_limit": False},
        {"tokens": 1500, "raise_rate_limit": False},
        {"tokens": 1500, "raise_rate_limit": False},
        {"tokens": 1500, "raise_rate_limit": False},
        # Call 6: Encounter a 429 RateLimitError (should rotate and retry)
        {"tokens": 1500, "raise_rate_limit": True},
        # Call 7-10: Exceed the daily limit threshold for keys
        {"tokens": 12000, "raise_rate_limit": False},
        {"tokens": 12000, "raise_rate_limit": False},
        {"tokens": 2000, "raise_rate_limit": False},
        {"tokens": 2000, "raise_rate_limit": False},
        # Call 11-15: Normal execution
        {"tokens": 1000, "raise_rate_limit": False},
        {"tokens": 1000, "raise_rate_limit": False},
        {"tokens": 1000, "raise_rate_limit": False},
        {"tokens": 1000, "raise_rate_limit": False},
        {"tokens": 1000, "raise_rate_limit": False},
    ]

    for key_info in test_rotator.keys_queue:
        # Patch the OpenAI client call method to simulate response / errors
        key_info.client.chat = MagicMock()
        key_info.client.chat.completions = MagicMock()
        
        def make_mock_create(k_info=key_info):
            def mock_create(model, messages, **kwargs):
                # Retrieve current test call spec
                if not mock_responses:
                    # Default callback if exhausted
                    response = MagicMock()
                    response.usage.total_tokens = 500
                    return response
                    
                call_spec = mock_responses[0]
                if call_spec["raise_rate_limit"]:
                    # Pop so next attempt gets the next spec
                    mock_responses.pop(0)
                    # Raise a RateLimitError
                    raise RateLimitError(
                        message="Rate limit reached. Please retry.",
                        response=MagicMock(status_code=429),
                        body={}
                    )
                
                # Consume spec
                mock_responses.pop(0)
                response = MagicMock()
                response.usage = MagicMock()
                response.usage.total_tokens = call_spec["tokens"]
                return response
            return mock_create
            
        key_info.client.chat.completions.create = make_mock_create()

    # Define a simulated calling helper
    async def make_llm_call():
        attempts = 0
        while attempts < 5:
            try:
                # Retrieve next client
                client = test_rotator.get_next_key()
                
                # Make API call (async completion mock)
                # Since it's a mock, we just call it synchronously or await it
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": "Hello!"}]
                )
                
                # Update usage metrics
                tokens = response.usage.total_tokens
                test_rotator.report_usage(tokens)
                return f"Success with {test_rotator.current_key.name} ({tokens} tokens)"
            except Exception as e:
                test_rotator.handle_error(e)
                attempts += 1
                logging.info(f"Retrying call flow... (attempt {attempts}/5)")
        raise Exception("Call failed after multiple retries.")

    # Execute 15 calls in a loop
    import asyncio
    async def main_test():
        for call_num in range(1, 16):
            logging.info(f"--- STARTING SIMULATED CALL #{call_num} ---")
            try:
                result = await make_llm_call()
                logging.info(f"Result: {result}")
            except AllKeysExhaustedException as e:
                logging.error(f"Halt: {e}")
                break
            except Exception as e:
                logging.error(f"Unexpected Failure: {e}")
                break
            # Slight delay to show delay check output
            await asyncio.sleep(0.1)
            
    asyncio.run(main_test())
