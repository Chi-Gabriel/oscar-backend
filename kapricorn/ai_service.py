# File: kapricorn/ai_service.py

from flask import current_app
import google.generativeai as genai
import logging
from .prompts import (
    extract_tags, string_to_dict, processVisualBotQuery,
    formatLocationInfo, analyseLocation
    
) # Add any other necessary imports from prompts.py

log = logging.getLogger(__name__)


def estimate_tokens(content):
    """Estimate token count. Prioritize text length."""
    # Adjust ratio based on observation or model specifics if known
    # Lower number = more tokens per char (safer estimate for limits)
    # Higher number = fewer tokens per char
    chars_per_token_estimate = 3.5 # General estimate
    image_token_estimate = 258 # Rough estimate for typical image input cost (Gemini 1.5 Flash?) - ADJUST AS NEEDED

    estimatedTotal = 0
    if isinstance(content, str):
        estimatedTotal = len(content) / chars_per_token_estimate
    elif isinstance(content, list): # Estimate history
        for message in content:
            if isinstance(message, dict) and 'parts' in message and isinstance(message['parts'], list):
                for part in message['parts']:
                    if isinstance(part, str):
                        estimatedTotal += len(part) / chars_per_token_estimate
                    elif isinstance(part, dict) and 'inline_data' in part:
                        # Add fixed estimate for images
                        estimatedTotal += image_token_estimate
            elif isinstance(message, str):
                estimatedTotal += len(message) / chars_per_token_estimate
    return round(estimatedTotal)

def _sanitize_part(part):
    """Checks if a part is valid for Google AI content."""
    if isinstance(part, str):
        return part # Text is valid
    elif isinstance(part, dict):
        # Check for valid inline_data structure
        if 'inline_data' in part and isinstance(part['inline_data'], dict):
            inline_data = part['inline_data']
            if 'mime_type' in inline_data and 'data' in inline_data:
                # Return only the valid structure
                return {'inline_data': {'mime_type': inline_data['mime_type'], 'data': inline_data['data']}}
        # Add checks for other valid Part types if needed (e.g., function calls)
    # If it's not a string or a valid known dictionary structure, it's invalid
    log.warning(f"Sanitizing invalid/unrecognized message part: {type(part)} Keys: {list(part.keys()) if isinstance(part, dict) else 'N/A'}")
    return None # Indicate removal
# --- End Helper Functions ---


def call_ai_model(prompt, model_name, api_key, stream=False):
    """Calls the Google AI model. Sanitizes history input including parts."""
    if not api_key:
        log.error(f"API Key is missing for model {model_name}.")
        return {"error": "AI service API key not configured."}
    if not model_name:
        log.error("AI Model name is missing.")
        return {"error": "AI service model name not configured."}

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        log.info(f"Calling AI model '{model_name}' (Stream: {stream})...")

        content_to_send = []
        if isinstance(prompt, str):
            # Basic text prompt
            content_to_send = [prompt] # Needs to be a list for generate_content
        elif isinstance(prompt, list):
            # Sanitize history list (assuming structure [{role:..., parts:...}])
            for message in prompt:
                if isinstance(message, dict) and 'role' in message and 'parts' in message:
                    sanitized_parts = []
                    if isinstance(message['parts'], list):
                        for part in message['parts']:
                            valid_part = _sanitize_part(part)
                            if valid_part is not None:
                                sanitized_parts.append(valid_part)
                    elif isinstance(message['parts'], str): # Allow simple string parts
                         sanitized_parts.append(message['parts'])
                    else:
                        log.warning(f"Message parts is not a list or string: {message['parts']}")
                        continue # Skip malformed message

                    if sanitized_parts:
                        content_to_send.append({
                            'role': message['role'],
                            'parts': sanitized_parts
                        })
                    else:
                        log.warning(f"Message skipped after part sanitization (no valid parts): Role={message.get('role','N/A')}")
                else:
                    log.warning(f"Skipping invalid history item (structure error): {type(message)}")
        else:
            log.error(f"Invalid prompt format type: {type(prompt)}")
            return {"error": "Invalid prompt format."}

        if not content_to_send:
            log.warning("No valid content to send to the AI model.")
            return {"error": "No valid content to send."}

        # --- Estimate Input Tokens ---
        input_token_count = 0
        try:
            # Use count_tokens if available and reliable, else estimate
            # count_result = model.count_tokens(content_to_send)
            # input_token_count = count_result.total_tokens
            input_token_count = model.count_tokens(content_to_send).total_tokens # Fallback/primary estimator
            log.debug(f"Estimated Input tokens for '{model_name}': {input_token_count}")
        except Exception as count_err:
             log.warning(f"Could not estimate input tokens for '{model_name}': {count_err}")
        # --- End Estimate Input Tokens ---

        response = model.generate_content(content_to_send, stream=stream)

        if stream:
             # For streaming, return the iterator and input count
             return {'stream': response, 'input_tokens': input_token_count}
        else:
            # For non-streaming, process the response fully
            output_token_count = 0
            generated_text = ""
            try:
                # Attempt to access text directly for non-streamed object
                # Handle potential blocks or errors in the response structure
                if hasattr(response, 'text'):
                    generated_text = response.text
                elif hasattr(response, 'parts'): # Check parts if text attribute isn't direct
                    generated_text = "".join(part.text for part in response.parts if hasattr(part, 'text'))
                else:
                    log.warning(f"AI response for '{model_name}' has unexpected structure: {response}")
                    # Try resolving if it's a prompt feedback issue
                    if hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                        reason = response.prompt_feedback.block_reason
                        log.error(f"AI response blocked. Reason: {reason}")
                        return {"error": f"AI response blocked due to: {reason}"}

                # Estimate output tokens
                if generated_text:
                    output_token_count = model.count_tokens(generated_text).total_tokens
                else:
                     log.warning(f"AI response for '{model_name}' was empty or inaccessible.")
                     # Check candidate status if available
                     if hasattr(response, 'candidates') and response.candidates:
                          finish_reason = response.candidates[0].finish_reason
                          if finish_reason != 1: # 1 = STOP, other values indicate issues (SAFETY, RECITATION, etc.)
                               log.error(f"AI generation finished abnormally. Reason: {finish_reason}")
                               return {"error": f"AI generation issue: {finish_reason}"}
                     # If still no text, return generic empty error
                     return {"error": "AI response was empty."}


            except Exception as resp_err:
                 log.error(f"Error processing non-streamed AI response for '{model_name}': {resp_err}", exc_info=True)
                 return {"error": "Error processing AI response."}

            log.info(f"AI model '{model_name}' non-stream successful. Input Est: {input_token_count}, Output Est: {output_token_count}")
            return {
                'text': generated_text,
                'input_tokens': input_token_count,
                'output_tokens': output_token_count
            }

    except genai.types.generation_types.BlockedPromptException as bpe:
         log.error(f"AI Model call blocked prompt ({model_name}): {bpe}", exc_info=True)
         return {"error": "AI request blocked by safety filters."}
    except Exception as e:
        log.error(f"AI Model call error ({model_name}, Stream: {stream}): {e}", exc_info=True)
        # More specific error check (e.g., API key validity) might be needed here
        return {"error": "AI service encountered an unexpected error."}


def get_chat_response(history, use_pro_model):
    """
    Gets a non-streaming chat response from the appropriate AI model.
    """
    log.debug(f"Getting chat response. Pro Model Requested: {use_pro_model}")

    if use_pro_model:
        model_name = current_app.config.get('PAID_MODEL_NAME')
        api_key = current_app.config.get('GOOGLE_API_KEY_PAID')
        log.debug(f"Using PAID model for chat: {model_name}")
    else:
        model_name = current_app.config.get('FREE_CHAT_MODEL_NAME')
        api_key = current_app.config.get('GOOGLE_API_KEY_FREE_CHAT')
        log.debug(f"Using FREE_CHAT model for chat: {model_name}")

    if not api_key or not model_name:
        log.error(f"Chat AI service config missing (Pro: {use_pro_model}). Key: {bool(api_key)}, Model: {bool(model_name)}")
        return {"error": "AI service not configured for this chat request."}

    # Use non-streaming for this specific function
    ai_result = call_ai_model(prompt=history, model_name=model_name, api_key=api_key, stream=False)

    return ai_result # Returns dict with 'text', 'input_tokens', 'output_tokens' or 'error'


def generate_schedule_data(gen_tag_content):
    """Calls the 'visualsBot' AI based on the parsed <gen> tag content."""
    log.debug(f"Generating schedule data from <gen> tag: {gen_tag_content}")

    # Parse the pipe-delimited content from the <gen> tag
    try:
        parts = gen_tag_content.split('|')
        if len(parts) != 5:
            raise ValueError(f"Expected 5 parts in <gen> tag, got {len(parts)}")
        crop_name, generation_type, location, current_date, npk_string = [p.strip() for p in parts]
    except Exception as e:
        log.error(f"Failed to parse <gen> tag content '{gen_tag_content}': {e}")
        return {"error": "Internal error: Invalid format in AI's generation request."}

    # Model/Key for Visuals Bot (Using FREE_ACCESSORY as configured)
    model_name = current_app.config.get('FREE_ACCESSORY_MODEL_NAME')
    api_key = current_app.config.get('GOOGLE_API_KEY_FREE_ACCESSORY')

    if not api_key or not model_name:
         log.error("AI service config missing for schedule generation (VisualsBot).")
         return {"error": "AI schedule generation service not configured."}

    # --- Build the prompt for VisualsBot ---
    # processVisualBotQuery expects a single string argument representing the user query part
    # The visualsBot prompt itself expects parameters within that string
    visuals_bot_input_string = f"Crop Name: {crop_name}\nGeneration Type: {generation_type}\nLocation: {location}\nCurrent Date: {current_date}\nNPK Readings: {npk_string}"
    prompt_content = processVisualBotQuery(visuals_bot_input_string)
    # --- End Prompt Build ---

    # Call AI (non-streaming)
    raw_response = call_ai_model(
        prompt=prompt_content, # Use the constructed prompt list for visuals bot
        model_name=model_name,
        api_key=api_key,
        stream=False
    )

    if 'error' in raw_response:
        log.warning(f"VisualsBot AI call failed: {raw_response['error']}")
        return raw_response # Forward error

    visuals_text = raw_response.get('text')
    if not visuals_text:
        log.warning("VisualsBot AI returned empty text.")
        return {"error": "AI failed to generate schedule structure."}

    # Extract content within <data> tag
    data_tag_content = extract_tags(visuals_text, ['data']).get('data')
    if not data_tag_content:
        log.error(f"Could not find <data> tag in VisualsBot response: {visuals_text[:300]}...")
        return {"error": "AI response format error (missing <data> tag)."}

    # Parse the JSON string inside <data>
    try:
        # Using string_to_dict helper (uses literal_eval/json.loads safely)
        schedule_json = string_to_dict(data_tag_content)
        log.info("Successfully parsed schedule data from VisualsBot.")
        # Add input tokens used by visuals bot to the result if needed
        schedule_json['_visuals_input_tokens'] = raw_response.get('input_tokens', 0)
        schedule_json['_visuals_output_tokens'] = raw_response.get('output_tokens', 0)
        return schedule_json # Return the parsed Python dictionary
    except Exception as e:
        log.error(f"Failed to parse JSON from <data> tag: {e}\nContent: {data_tag_content[:300]}...", exc_info=True)
        return {"error": "AI response format error (invalid JSON in <data> tag)."}
    
    

def get_recommendations(location_description):
    """
    Generates crop recommendations using AI based on location.
    Uses the FREE_ACCESSORY model configured in the app.

    Args:
        location_description (str): Description of the location (e.g., "Ibadan, Oyo, Nigeria").

    Returns:
        dict: Parsed crop data {crop_name: {details...}} on success.
        dict: An error dictionary {'error': message} on failure.
    """
    log.debug(f"Getting recommendations for location '{location_description}'")

    # --- Determine Model/Key (Using FREE_ACCESSORY model for recommendations) ---
    model_name = current_app.config.get('PAID_MODEL_NAME')
    api_key = current_app.config.get('GOOGLE_API_KEY_RECOMENDATIONS')
    log.debug(f"Using FREE_ACCESSORY model for recommendations: {model_name}")

    if not api_key or not model_name:
        log.error(f"AI service config missing for recommendations (FREE_ACCESSORY)")
        return {"error": "AI recommendations service not configured."}

    # --- Step 1: Initial Analysis Prompt ---
    try:
        # analyseLocation returns a tuple (prompt, parser_function), we only need the prompt here
        analysis_prompt, _ = analyseLocation(location_description)
        log.debug("Generated analysis prompt.")
    except Exception as e:
        log.error(f"Error building analysis prompt: {e}", exc_info=True)
        return {"error": "Internal error preparing recommendation request (1)."}

    # --- Call AI for Analysis ---
    log.info(f"Calling AI for recommendation analysis (Model: {model_name})...")
    analysis_result = call_ai_model(
        prompt=analysis_prompt,
        model_name=model_name,
        api_key=api_key,
        stream=False # Recommendations don't need streaming
    )

    if 'error' in analysis_result:
        log.warning(f"AI analysis call failed for recommendations: {analysis_result['error']}")
        return analysis_result # Forward the error

    analysis_text = analysis_result.get('text')
    input_tokens_step1 = analysis_result.get('input_tokens', 0)
    output_tokens_step1 = analysis_result.get('output_tokens', 0)

    if not analysis_text:
         log.warning("AI analysis for recommendations returned empty text.")
         return {"error": "AI analysis failed to produce results."}
    log.debug("Received analysis text from AI.")

    # --- Step 2: Formatting Prompt ---
    try:
        # formatLocationInfo returns a tuple (prompt, parser_function), we need both
        formatting_prompt, response_parser = formatLocationInfo(analysis_text)
        log.debug("Generated formatting prompt.")
    except Exception as e:
        log.error(f"Error building formatting prompt: {e}", exc_info=True)
        return {"error": "Internal error preparing recommendation request (2)."}

    # --- Call AI for Formatting ---
    # Using the same model for simplicity, though a cheaper one could be used.
    model_name= current_app.config.get('FREE_ACCESSORY_MODEL_NAME')
    api_key= current_app.config.get('GOOGLE_API_KEY_FREE_ACCESSORY')
    log.info(f"Calling AI for recommendation formatting (Model: {model_name})...")
    formatting_result = call_ai_model(
        prompt=formatting_prompt,
        model_name=model_name,
        api_key=api_key,
        stream=False
    )

    if 'error' in formatting_result:
        log.warning(f"AI formatting call failed for recommendations: {formatting_result['error']}")
        return formatting_result

    formatted_text = formatting_result.get('text')
    input_tokens_step2 = formatting_result.get('input_tokens', 0)
    output_tokens_step2 = formatting_result.get('output_tokens', 0)

    if not formatted_text:
         log.warning("AI formatting for recommendations returned empty text.")
         return {"error": "AI formatting failed to produce results."}
    log.debug("Received formatted text from AI.")

    # --- Step 3: Parse Formatted Text ---
    try:
        # The response_parser here should be extractCropsInfo from formatLocationInfo
        parsed_recommendations = response_parser(formatted_text)
        if not parsed_recommendations or not isinstance(parsed_recommendations, dict):
             # Add specific check if parser returns non-dict or empty
             raise ValueError(f"Parsing resulted in invalid data type or empty dict: {type(parsed_recommendations)}")
        log.info(f"Successfully generated and parsed {len(parsed_recommendations)} recommendations.")

        # Add token usage info to the result for tracking/debugging
        parsed_recommendations['_total_input_tokens'] = input_tokens_step1 + input_tokens_step2
        parsed_recommendations['_total_output_tokens'] = output_tokens_step1 + output_tokens_step2

        return parsed_recommendations # Return the structured dictionary
    except Exception as e:
        log.error(f"Error parsing formatted AI recommendations: {e}\nRaw Formatted Text:\n{formatted_text}", exc_info=True) # Log more text
        return {"error": "Internal error processing AI recommendation results."}