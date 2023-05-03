from .. import gcp
from ..config import get_instance_config


def gcr_grant(project, instance_name, needs_write_access):
    config = get_instance_config(instance_name)
    gcp.grant_access_to_gcr(project, instance_name, needs_write_access)


def add_command(subparser):
    def _gcr_grant(args):
        gcr_grant(args.project, args.name, args.push)

    parser = subparser.add_parser(
        "gcr-grant",
        help="grant access to pull (and optionally push) to GCR docker repo in specified project",
    )
    parser.set_defaults(func=_gcr_grant)
    parser.add_argument(
        "project",
        help="The project containing the GCR repo that you want the instance to have access to",
    )
    parser.add_argument(
        "name",
        help="The name of the instance that you want to have access to use the GCR repo",
        nargs="?",
        default="default",
    )
    parser.add_argument(
        "--push",
        help="If specified, will grant access to push to repo as well as read from repo",
        action="store_true",
    )
