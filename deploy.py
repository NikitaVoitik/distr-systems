import os
import uuid
import boto3
import time
import argparse
import requests
from dotenv import load_dotenv

load_dotenv()


class EC2Manager:
    def __init__(self, region_name='us-west-2'):
        self.ec2 = boto3.resource('ec2', region_name=region_name)
        self.ssm_client = boto3.client('ssm', region_name=region_name)

    def _get_latest_ami_id(self, base_os='amazon-linux'):
        if base_os == 'amazon-linux':
            parameter_name = '/aws/service/ami-amazon-linux-latest/amzn2-ami-hvm-x86_64-gp2'
        else:
            raise ValueError(f"Unsupported base OS: {base_os}")

        response = self.ssm_client.get_parameter(Name=parameter_name)
        return response['Parameter']['Value']

    def create_key(self):
        key_name = f"key-{uuid.uuid4()}"
        key_pair = self.ec2.create_key_pair(KeyName=key_name)

        with open(f"{key_name}.pem", 'w') as key_file:
            key_file.write(key_pair.key_material)

        os.chmod(f"{key_name}.pem", 0o400)

        print("Created key pair:", key_name)

        return key_pair

    def create_security_group(self):
        group_name = f"{uuid.uuid4()}"

        security_group = self.ec2.create_security_group(
            GroupName=group_name,
            Description='Security group for web server'
        )

        security_group.authorize_ingress(
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                },
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 80,
                    'ToPort': 80,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                }
            ]
        )

        print("Created security group:", group_name)
        return security_group.id

    def launch_instance(self, key_name, security_group_id, ami_id, custom_ami=False):
        with open('main.py', 'r') as f:
            app_code = f.read()

        if custom_ami:
            user_data = f"""#!/bin/bash
cd /home/ec2-user/app

uvicorn main:app --host 0.0.0.0 --port 80
"""
        else:
            user_data = f"""#!/bin/bash
yum update -y
yum install -y python3-pip
pip3 install fastapi uvicorn httpx

mkdir /home/ec2-user/app
cd /home/ec2-user/app

cat <<'EOF' > main.py
{app_code}
EOF

uvicorn main:app --host 0.0.0.0 --port 80
"""
        start_time = time.time()

        instance = self.ec2.create_instances(
            ImageId=ami_id,
            InstanceType='t2.micro',
            MinCount=1,
            MaxCount=1,
            KeyName=key_name,
            SecurityGroupIds=[security_group_id],
            UserData=user_data
        )[0]

        print(f"Launching instance {instance.id}...")

        instance.wait_until_running()
        instance.reload()
        running_time = time.time()

        app_ready_time = self.wait_for_app_ready(instance.public_ip_address)

        print(f"Instance {instance.id} is running at {instance.public_ip_address}")
        print(f"Time to running state: {running_time - start_time:.2f} seconds")
        print(f"Time to app ready: {app_ready_time - start_time:.2f} seconds")

        return instance

    def wait_for_app_ready(self, host, timeout=300):
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"http://{host}/shifts", timeout=5)
                if response.status_code == 200:
                    return time.time()
            except:
                pass
            time.sleep(1)

        return time.time()

def main():
    parser = argparse.ArgumentParser()
    ami_group = parser.add_mutually_exclusive_group(required=True)
    ami_group.add_argument(
        '--linux_base',
        type=str,
        choices=['amazon-linux'],
        help='The base Linux distribution for the EC2 instance. Currently, only "amazon-linux" is supported.'
    )
    ami_group.add_argument(
        '--linux_custom',
        type=str,
        help='The custom AMI ID to use for the EC2 instance.'
    )

    args = parser.parse_args()

    ec2_manager = EC2Manager()
    ami_id = None
    custom_ami = False

    if args.linux_custom:
        ami_id = args.linux_custom
        custom_ami = True
    elif args.linux_base:
        try:
            ami_id = ec2_manager._get_latest_ami_id(args.linux_base)
        except ValueError as e:
            print(e)
            return

    if not ami_id:
        print("Could not determine the AMI ID. Exiting.")
        return

    key_pair = ec2_manager.create_key()
    security_group_id = ec2_manager.create_security_group()
    ec2_manager.launch_instance(key_pair.name, security_group_id, ami_id, custom_ami=custom_ami)


if __name__ == '__main__':
    main()