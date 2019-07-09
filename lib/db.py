import os

import boto3

DYNAMODB_URL = os.environ.get("DYNAMODB_URL", "http://localhost:8000")

# for use imported elsewhere
dynamo = boto3.resource('dynamodb', endpoint_url=DYNAMODB_URL, region_name='us-east-1')
reports = dynamo.Table('taine.reports')
reportnums = dynamo.Table('taine.reportnums')


async def query(table, filter_exp):
    sentinel = lek = object()
    while lek is not None:
        if lek is sentinel:
            response = table.scan(
                FilterExpression=filter_exp,
            )
        else:
            response = table.scan(
                FilterExpression=filter_exp,
                ExclusiveStartKey=lek
            )

        lek = response.get('LastEvaluatedKey')
        for report_data in response['Items']:
            yield report_data


# set up the tables
async def _setup():
    reports_table = dynamo.create_table(
        TableName='taine.reports',
        KeySchema=[
            {
                'AttributeName': 'report_id',
                'KeyType': 'HASH'  # Partition key
            }
        ],
        GlobalSecondaryIndexes=[
            {
                'IndexName': 'message_id',
                'KeySchema': [
                    {
                        'AttributeName': 'message',
                        'KeyType': 'HASH'
                    },
                ],
                'Projection': {
                    'ProjectionType': 'ALL',
                },
                'ProvisionedThroughput': {
                    'ReadCapacityUnits': 10,
                    'WriteCapacityUnits': 10
                }
            },
            {
                'IndexName': 'github_issue',
                'KeySchema': [
                    {
                        'AttributeName': 'github_issue',
                        'KeyType': 'HASH'
                    },
                    {
                        'AttributeName': 'github_repo',
                        'KeyType': 'RANGE'
                    },
                ],
                'Projection': {
                    'ProjectionType': 'ALL',
                },
                'ProvisionedThroughput': {
                    'ReadCapacityUnits': 10,
                    'WriteCapacityUnits': 10
                }
            },
        ],
        AttributeDefinitions=[
            {
                'AttributeName': 'report_id',
                'AttributeType': 'S'
            },
            {
                'AttributeName': 'message',
                'AttributeType': 'N'
            },
            {
                'AttributeName': 'github_issue',
                'AttributeType': 'N'
            },
            {
                'AttributeName': 'github_repo',
                'AttributeType': 'S'
            },
        ],
        ProvisionedThroughput={
            'ReadCapacityUnits': 10,
            'WriteCapacityUnits': 10
        }
    )
    print(reports_table)

    # schema:
    # {
    #     "identifier": "AVR",
    #     "num": 123
    # }
    report_nums_table = dynamo.create_table(
        TableName='taine.reportnums',
        KeySchema=[
            {
                'AttributeName': 'identifier',
                'KeyType': 'HASH'  # Partition key
            }
        ],
        AttributeDefinitions=[
            {
                'AttributeName': 'identifier',
                'AttributeType': 'S'
            },
        ],
        ProvisionedThroughput={
            'ReadCapacityUnits': 10,
            'WriteCapacityUnits': 10
        }
    )
    print(report_nums_table)


if __name__ == '__main__':
    import asyncio

    asyncio.get_event_loop().run_until_complete(_setup())
