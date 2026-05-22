"""list — list AWS resources by type, filter by tag / missing-tag.

WHAT YOU MUST BUILD
-------------------
Support 4 resource types: ec2, rds, s3, volume.
Each takes:
- `want` — list of (key, value) tag pairs the resource MUST have
- `missing` — list of tag keys the resource MUST NOT have

Print a formatted table to stdout. Test cases are in tests/test_list.py.

HELPERS YOU CAN USE
-------------------
From commands._common:
  parse_kv(s) -> (k, v)            # "Owner=alice" -> ("Owner", "alice")
  tags_to_dict(items) -> dict       # boto3 [{"Key","Value"}] -> {k: v}
  tags_match(tags, want, missing) -> bool

AWS APIS YOU'LL NEED
--------------------
- EC2: ec2.describe_instances() with get_paginator
- RDS: rds.describe_db_instances(), then list_tags_for_resource(ResourceName=arn)
- S3:  s3.list_buckets(), then get_bucket_tagging(Bucket=name)
       (catch ClientError when bucket has no tagging config — treat as {})
- EBS: ec2.describe_volumes() with get_paginator

EXPECTED OUTPUT FORMAT (when run from CLI)
------------------------------------------
    EC2 Environment=dev — 1 found:
    ------------------------------------------------------------------------------
      i-0abc123def456789a       t3.micro       running       Environment=dev

VERIFY
------
    pytest tests/test_list.py -v
"""
import boto3

from commands._common import parse_kv, tags_to_dict, tags_match


def _list_ec2(want, missing):
    """List EC2 instances matching tag filters.

    Args:
        want: list of (key, value) tag pairs that must all match
        missing: list of tag keys that must NOT be present

    Returns:
        list of (instance_id, instance_type, state, tags_dict) tuples
    """
    ec2 = boto3.client("ec2")
    paginator = ec2.get_paginator("describe_instances")
    rows = []
    for page in paginator.paginate():
        for reservation in page["Reservations"]:
            for inst in reservation["Instances"]:
                tags = tags_to_dict(inst.get("Tags", []))
                if tags_match(tags, want, missing):
                    rows.append((
                        inst["InstanceId"],
                        inst["InstanceType"],
                        inst["State"]["Name"],
                        tags,
                    ))
    return rows


def _list_rds(want, missing):
    """Same shape as _list_ec2 but for RDS DB instances.

    Note: RDS tags require a separate API call per DB:
        rds.list_tags_for_resource(ResourceName=db['DBInstanceArn'])

    Returns:
        list of (db_id, db_class, db_status, tags_dict) tuples
    """
    rds = boto3.client("rds")
    paginator = rds.get_paginator("describe_db_instances")
    rows = []
    for page in paginator.paginate():
        for db in page["DBInstances"]:
            tag_list = rds.list_tags_for_resource(
                ResourceName=db["DBInstanceArn"]
            )["TagList"]
            tags = tags_to_dict(tag_list)
            if tags_match(tags, want, missing):
                rows.append((
                    db["DBInstanceIdentifier"],
                    db["DBInstanceClass"],
                    db["DBInstanceStatus"],
                    tags,
                ))
    return rows


def _list_s3(want, missing):
    """List S3 buckets matching tag filters.

    Note: get_bucket_tagging raises ClientError if no tagging config exists
    for that bucket. Treat that as an empty tags dict, not an error.

    Returns:
        list of (bucket_name, "bucket", "active", tags_dict) tuples
    """
    from botocore.exceptions import ClientError

    s3 = boto3.client("s3")
    buckets = s3.list_buckets().get("Buckets", [])
    rows = []
    for b in buckets:
        name = b["Name"]
        try:
            tag_set = s3.get_bucket_tagging(Bucket=name)["TagSet"]
        except ClientError:
            tag_set = []
        tags = tags_to_dict(tag_set)
        if tags_match(tags, want, missing):
            rows.append((name, "bucket", "active", tags))
    return rows


def _list_volume(want, missing):
    """List EBS volumes matching tag filters.

    Returns:
        list of (volume_id, "<type>-<size>GB", state, tags_dict) tuples
        e.g. ("vol-0abc", "gp2-100GB", "in-use", {"purpose": "practice"})
    """
    ec2 = boto3.client("ec2")
    paginator = ec2.get_paginator("describe_volumes")
    rows = []
    for page in paginator.paginate():
        for vol in page["Volumes"]:
            tags = tags_to_dict(vol.get("Tags", []))
            if tags_match(tags, want, missing):
                type_size = f"{vol['VolumeType']}-{vol['Size']}GB"
                rows.append((
                    vol["VolumeId"],
                    type_size,
                    vol["State"],
                    tags,
                ))
    return rows


DISPATCH = {
    "ec2": _list_ec2,
    "rds": _list_rds,
    "s3": _list_s3,
    "volume": _list_volume,
}


def run(args):
    """Entry point called by costctl.py.

    Steps you should perform:
      1. Convert args.tag (list of "k=v" strings) → want pairs via parse_kv
      2. Use args.missing_tag (list of keys) as-is
      3. Call DISPATCH[args.type](want, missing) → rows
      4. Print a header line, separator, then one row per resource

    Args set by argparse:
        args.type         — one of "ec2", "rds", "s3", "volume"
        args.tag          — list[str], each "key=value"
        args.missing_tag  — list[str], each "key"
    """
    want = [parse_kv(t) for t in (args.tag or [])]
    missing = args.missing_tag or []
    rows = DISPATCH[args.type](want, missing)

    # Build header
    resource_type = args.type.upper()
    filters = " ".join(f"{k}={v}" for k, v in want)
    if missing:
        filters += (" " if filters else "") + "missing:" + ",".join(missing)
    header = f"  {resource_type} {filters}".rstrip() + f" — {len(rows)} found:"
    print(header)
    print("  " + "-" * 78)

    for rid, rtype, state, tags in rows:
        tag_str = "  ".join(f"{k}={v}" for k, v in sorted(tags.items()))
        print(f"    {rid:<30s} {rtype:<15s} {state:<15s} {tag_str}")
