# File: kapricorn/routes/recommendation_routes.py

from flask import request, jsonify, Blueprint
import logging
from ..ai_service import get_recommendations

log = logging.getLogger(__name__)

# Create a new Blueprint for recommendation routes
recommend_bp = Blueprint('recommend', __name__, url_prefix='/api/recommend')

@recommend_bp.route('/crops', methods=['POST'])
def crop_recommendations():
    """Endpoint to get crop recommendations based on location."""
    data = request.json
    if not data:
        return jsonify({"error": "Invalid request: No JSON body found"}), 400

    location = data.get('location')
    if not location or not isinstance(location, str) or not location.strip():
        return jsonify({"error": "Invalid request: 'location' field (string) is required"}), 400

    log.info(f"Received crop recommendation request for location: {location}")

    try:
        result = get_recommendations(location.strip())

        if 'error' in result:
            log.error(f"Recommendation service returned error: {result['error']}")
            # Determine status code based on error if possible, default 500
            status_code = 500
            if "not configured" in result['error']:
                 status_code = 503 # Service Unavailable
            return jsonify({"error": result['error']}), status_code
        else:
            # Extract token info before sending
            input_tokens = result.pop('_total_input_tokens', 0)
            output_tokens = result.pop('_total_output_tokens', 0)

            log.info(f"Successfully generated recommendations. Input Tokens: {input_tokens}, Output Tokens: {output_tokens}")
            # The result is already the dictionary of crops {crop: {details...}}
            return jsonify({
                "recommendations": result,
                "_input_tokens": input_tokens,
                "_output_tokens": output_tokens
                }), 200

    except Exception as e:
        log.exception(f"Unexpected error during crop recommendation for location '{location}': {e}") # Log full traceback
        return jsonify({"error": "An unexpected internal server error occurred."}), 500