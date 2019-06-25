import aioboto3

# for use imported elsewhere
dynamo = aioboto3.resource('dynamodb', endpoint_url="http://localhost:8000")
reports = dynamo.Table('taine.reports')
reportnums = dynamo.Table('taine.reportnums')


# set up the tables
async def _setup():
    reports_table = await dynamo.create_table(
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
    report_nums_table = await dynamo.create_table(
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

    await dynamo.close()


if __name__ == '__main__':
    import asyncio

    asyncio.get_event_loop().run_until_complete(_setup())
