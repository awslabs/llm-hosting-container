import uuid
import boto3
# This script helps you to enable SSM access to the endpoint so we can debug the
# container level issues there
def main():
    session = boto3.Session()
    client = session.client("sagemaker", region_name="us-west-2")

    # List existing endpoints
    print("Listing endpoints:")
    print(client.list_endpoints())
    print()

    # Get endpoint name
    endpoint_name = client.list_endpoints()["Endpoints"][0]["EndpointName"]
    print(f"Endpoint name: {endpoint_name}\n")

    # Describe endpoint
    response = client.describe_endpoint(EndpointName=endpoint_name)
    endpoint_config_name = response["EndpointConfigName"]

    # Check if EnableSSMAccess is currently enabled
    current_ssm_access = response["ProductionVariants"][0].get("EnableSSMAccess", False)
    print(f"Current EnableSSMAccess status: {current_ssm_access}\n")

    # Generate new endpoint config name
    new_endpoint_config_name = f"{endpoint_config_name.split('-')[0]}-{str(uuid.uuid4())[:11]}"

    # Update EnableSSMAccess to True in new production variant
    new_production_variants = response["ProductionVariants"]
    new_production_variants[0]["EnableSSMAccess"] = True

    # Create new endpoint config
    create_endpoint_config_response = client.create_endpoint_config(
        EndpointConfigName=new_endpoint_config_name,
        ProductionVariants=new_production_variants,
    )
    print(f"Created new endpoint config: {create_endpoint_config_response}\n")

    # Describe new endpoint config
    new_endpoint_config_response = client.describe_endpoint_config(
        EndpointConfigName=new_endpoint_config_name
    )
    print(f"New endpoint config: {new_endpoint_config_response}\n")

    # Update endpoint with new endpoint config
    update_endpoint_response = client.update_endpoint(
        EndpointName=endpoint_name, EndpointConfigName=new_endpoint_config_name
    )
    print(update_endpoint_response)

if __name__ == "__main__":
    main()