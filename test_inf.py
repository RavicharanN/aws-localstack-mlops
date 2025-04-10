import json
import requests

def test_inference_api():
    # Update this URL if your API is hosted elsewhere
    endpoint = "http://localhost:8000/infer"
    
    # The payload includes the S3 image path (adjust the value as needed)
    payload = {
        "s3_path": "s3://test-images/2.jpg"
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(endpoint, data=json.dumps(payload), headers=headers)
        print("Status Code:", response.status_code)
        try:
            # Attempt to decode the response as JSON
            response_data = response.json()
            print("Response JSON:", json.dumps(response_data, indent=2))
        except Exception as json_err:
            # If it fails to decode, print the raw text
            print("Response Text:", response.text)
    except Exception as e:
        print("Error making request:", str(e))

if __name__ == "__main__":
    test_inference_api()
