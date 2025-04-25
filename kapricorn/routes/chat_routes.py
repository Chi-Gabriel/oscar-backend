# File: kapricorn/routes/chat_routes.py

from flask import request, jsonify, current_app
import logging
from . import chat_bp  # Import the blueprint
from ..ai_service import get_chat_response, generate_schedule_data
from ..prompts import processChats, extract_tags, formatVisualBotResponse, startChats

log = logging.getLogger(__name__)

@chat_bp.route('/', methods=['POST'])
def handle_chat():
    """Handles incoming chat messages."""
    data = request.json
    if not data:
        return jsonify({"error": "Invalid request: No JSON body found"}), 400

    user_message = data.get('message')
    history = data.get('history', []) # Expecting list of {'role': ..., 'parts': [...]}
    use_pro_model = data.get('use_pro_model', False) # Default to free model
    location = data.get('location') # Optional context
    npk = data.get('npk')           # Optional context
    current_date = data.get('date') # Optional context

    if not user_message:
        return jsonify({"error": "Invalid request: 'message' field is required"}), 400
    if not isinstance(history, list):
         return jsonify({"error": "Invalid request: 'history' must be a list"}), 400

    # Append the current user message to the history before processing
    # Ensure it follows the expected structure
    current_turn = {'role': 'user', 'parts': [user_message]} # Simple text part
    history.append(current_turn)

    # Prepare the history for the AI using processChats
    # processChats adds system context (<g>) and prepends initial bot setup (startChats)
    try:
        processed_history = processChats(history, npk=npk, location=location, date=current_date)
    except Exception as e:
        log.error(f"Error processing chat history: {e}", exc_info=True)
        return jsonify({"error": "Internal server error processing chat history"}), 500

    # Call the AI service to get the response
    ai_result = get_chat_response(processed_history, use_pro_model)

    if 'error' in ai_result:
        log.error(f"AI service returned error: {ai_result['error']}")
        # Provide a generic error to the frontend, but log the specific one
        return jsonify({"error": "Failed to get response from AI service."}), 500

    ai_raw_text = ai_result.get('text')
    if not ai_raw_text:
        log.error("AI service returned empty text response.")
        return jsonify({"error": "AI service returned an empty response."}), 500

    # --- Parse AI response for tags ---
    try:
        extracted = extract_tags(ai_raw_text) # Default tags: ['p', 'g', 'r', 'gr', 'cls', 'gen']
        ai_response_text = extracted.get('r') # Get the primary response content
        gen_tag_content = extracted.get('gen')
        classification = extracted.get('cls')
        # We also need the model's full response for the history
        model_full_response_part = {'role': 'model', 'parts': [ai_raw_text]}

    except Exception as e:
        log.error(f"Error parsing AI response tags: {e}\nRaw Text: {ai_raw_text[:200]}...", exc_info=True)
        # Still try to return the raw text if parsing fails, but add it to history
        history.append({'role': 'model', 'parts': [f"[System Error: Could not parse AI tags] {ai_raw_text}"]})
        return jsonify({
            "response": ai_raw_text, # Send raw text back
            "history": history, # Include the errored response in history
            "classification": None,
            "error": "Error parsing AI response format." # Add an error flag
            }), 200 # Return 200 but indicate parsing error


    # --- Handle <gen> tag if present ---
    visuals_data = None
    if gen_tag_content:
        log.info(f"Detected <gen> tag. Requesting schedule data: {gen_tag_content}")
        schedule_result = generate_schedule_data(gen_tag_content)

        if 'error' in schedule_result:
            log.error(f"Failed to generate schedule data: {schedule_result['error']}")
            # Inform the user the generation failed via a system message in history
            system_error_msg = f"<g>System: Failed to generate the requested visual data. Error: {schedule_result['error']}. Please continue the conversation.</g>"
            user_msg_part, bot_msg_part, _ = formatVisualBotResponse(system_error_msg) # Use formatVisualBotResponse to structure it

            # Append original model response (acknowledgment) + system error message
            history.append(model_full_response_part) # Oscar's original "<r> Generating..."
            history.append({'role': 'user', 'parts': [user_msg_part]}) # System message framed as user input for next turn
            history.append({'role': 'model', 'parts': [bot_msg_part]}) # Oscar acknowledging the system message
            # Fall through to return the original AI response text ('<r>')
        else:
            log.info("Successfully generated schedule data.")
            visuals_data = schedule_result # This is the parsed JSON data
            # Add system message indicating success to history
            system_success_msg = f"<g>System: Visual data generated successfully. Displaying now. You can ask follow-up questions.</g>"
            user_msg_part, bot_msg_part, _ = formatVisualBotResponse(system_success_msg) # Use formatter

            # Append original model response + system success message
            history.append(model_full_response_part) # Oscar's original "<r> Generating..."
            history.append({'role': 'user', 'parts': [user_msg_part]})
            history.append({'role': 'model', 'parts': [bot_msg_part]})
            # The visuals_data will be returned in the main JSON response
    else:
        # No <gen> tag, just append the normal AI response to history
        history.append(model_full_response_part)


    # --- Prepare final response ---
    response_payload = {
        "response": ai_response_text or "...", # Use <r> content, fallback if missing
        "history": history, # Return the updated history
        "classification": classification,
        "visuals_data": visuals_data # Will be null if <gen> wasn't processed or failed gracefully
    }

    # Add token info for potential debugging/tracking on frontend if needed
    response_payload["_input_tokens"] = ai_result.get('input_tokens', 0)
    response_payload["_output_tokens"] = ai_result.get('output_tokens', 0)
    if visuals_data and isinstance(visuals_data, dict):
         response_payload["_visuals_input_tokens"] = visuals_data.pop('_visuals_input_tokens', 0)
         response_payload["_visuals_output_tokens"] = visuals_data.pop('_visuals_output_tokens', 0)

    return jsonify(response_payload), 200