# EC2 Manager

A Python script to automatically launch and configure EC2 instances with a FastAPI application.

## Prerequisites

- Python 3.6+
- AWS CLI configured with appropriate credentials
- AWS account with EC2 permissions

## Installation

1. Clone or download the script
2. Install required dependencies:

```bash
pip install boto3 requests python-dotenv
```

3. Set up AWS credentials (one of the following methods):
    - AWS CLI: `aws configure`
    - .env file with `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
    - Environment variables: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`

## Usage

### Using Amazon Linux Base Image

```bash
python ec2_manager.py --linux_base amazon-linux --region us-east-1
```

### Using Custom AMI

```bash
python ec2_manager.py --linux_custom ami-1234567890abcdef0 --region eu-west-2
```

## Command Line Arguments

| Argument | Description | Required | Options |
|----------|-------------|----------|---------|
| `--linux_base` | Base Linux distribution | Yes* | `amazon-linux` |
| `--linux_custom` | Custom AMI ID | Yes* | Any valid AMI ID |
| `--region` | AWS region to deploy to | No | Any valid AWS region (e.g., `us-east-1`, `eu-west-2`, `us-west-3`) |

*One of `--linux_base` or `--linux_custom` is required (mutually exclusive)

## What the Script Does

1. **Creates SSH Key Pair**: Generates a unique SSH key pair and saves the private key as a `.pem` file
2. **Creates Security Group**: Sets up a security group allowing:
    - SSH access (port 22) from anywhere
    - HTTP access (port 80) from anywhere
3. **Launches EC2 Instance**:
    - Instance type: `t2.micro`
    - Installs Python, FastAPI, and uvicorn (for base images)
    - Copies your `main.py` application code
    - Starts the FastAPI server on port 80
4. **Monitors Deployment**: Tracks timing for instance launch and application readiness

## Output

The script provides detailed output including:
- Created key pair name
- Security group ID
- Instance ID and public IP address
- Time to reach running state
- Time until application is ready

Example output:
```
Created key pair: key-12345678-1234-1234-1234-123456789012
Created security group: 87654321-4321-4321-4321-210987654321
Launching instance i-0abcdef1234567890...
Instance i-0abcdef1234567890 is running at 54.123.45.67
Time to running state: 45.32 seconds
Time to app ready: 125.67 seconds
```