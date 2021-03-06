# flake8: noqa
import argparse
import asyncio
import logging
import os
import re
from xml.dom import minidom

from .. import asutil, exception

logger = logging.getLogger(__name__)

REPOUR_JAVA_KEY = "-DRepour_Java="

stdout_options = asutil.process_stdout_options
stderr_options = asutil.process_stderr_options


def get_removed_repos(work_dir, parameters):
    """
    Parses the filename of the removed repos backup file from the parameters list and if there
    is one, it reads the list of repos and returns it.
    """
    result = []

    pattern = re.compile("-DrepoRemovalBackup[ =](.+)")
    for parameter in parameters:
        m = pattern.match(parameter)
        if m is not None:
            filepath = os.path.join(work_dir, m.group(1))
            logger.debug(
                "Files and folders in the work directory:\n  %s", os.listdir(work_dir)
            )

            if os.path.exists(filepath):
                tree = minidom.parse(filepath)
                for repo_elem in tree.getElementsByTagName("repository"):
                    repo = {
                        "releases": True,
                        "snapshots": True,
                        "name": "",
                        "id": "",
                        "url": "",
                    }
                    for enabled_elem in repo_elem.getElementsByTagName("enabled"):
                        if enabled_elem.parentNode.localName in [
                            "releases",
                            "snapshots",
                        ]:
                            bool_value = enabled_elem.childNodes[0].data == "true"
                            repo[enabled_elem.parentNode.localName] = bool_value
                    for tag in ["id", "name", "url"]:
                        for elem in repo_elem.getElementsByTagName(tag):
                            if elem.childNodes:
                                repo[tag] = elem.childNodes[0].data
                    result.append(repo)
                break
            else:
                logger.info(
                    "File %s does not exist. It seems no repositories were removed",
                    filepath,
                )

    logger.info("Removed repos are: " + str(result))
    return result


def is_temp_build(adjustspec):
    """ For temp build to be active, we need to both provide a 'is_temp_build' key
        in our request and its value must be true

        return: :bool: whether temp build feature enabled or not
    """
    key = "tempBuild"
    if (key in adjustspec) and adjustspec[key] is True:
        return True
    else:
        return False


def get_specific_indy_group(adjustspec, adjust_provider_config):
    temp_build_enabled = is_temp_build(adjustspec)

    if temp_build_enabled:
        return adjust_provider_config.get("temp_build_indy_group", None)
    else:
        return None


def get_temp_build_timestamp(adjustspec):
    """ Find the timestamp to provide to PME from the adjust request.

        If the timestamp is set *AND* the temp_build key is set to true, then
        this function returns the value of the timestamp.

        Otherwise it will return None
    """
    temp_build_timestamp_key = "tempBuildTimestamp"
    temp_build_timestamp = None

    temp_build_enabled = is_temp_build(adjustspec)

    if temp_build_timestamp_key in adjustspec:
        temp_build_timestamp = adjustspec[temp_build_timestamp_key]

    if temp_build_timestamp is None:
        temp_build_timestamp = "temporary"

    if temp_build_enabled:
        logger.info("Temp build timestamp set to: " + str(temp_build_timestamp))
        return temp_build_timestamp
    else:
        return None


def get_extra_parameters(extra_adjust_parameters):
    """
    Get the extra build configuration parameters from PNC
    If the parameters contain '--file=<folder>/pom.xml', then extract that folder
    and remove that --file option from the list of extra params.
    In PME 2.11 and PME 2.12, there is a bug where that option causes the file target/pom-manip-ext-result.json
    to be badly generated. Fixed in PME 2.13+
    See: PRODTASKS-361
    Returns: tuple<list<string>, string>: list of params(minus the --file option), and folder where to run PME
    If '--file' option not used, the folder will be an empty string
    """
    subfolder = ""

    paramsString = extra_adjust_parameters.get("ALIGNMENT_PARAMETERS", None)
    if paramsString is None:
        return [], subfolder
    else:

        parser = argparse.ArgumentParser()
        parser.add_argument("-f", "--file")
        (options, remaining_args) = parser.parse_known_args(paramsString.split())

        if options.file is not None:
            subfolder = options.file.replace("pom.xml", "")

        return remaining_args, subfolder


def get_jvm_from_extra_parameters(extra_parameters):
    """
    If repour JVM option specified, return the option value. Otherwise return None
    """

    for parameter in extra_parameters:

        if REPOUR_JAVA_KEY in parameter:
            return parameter.replace(REPOUR_JAVA_KEY, "")
    else:
        return None


async def print_java_version(java_bin_dir=""):

    if java_bin_dir and java_bin_dir.endswith("/"):
        command = java_bin_dir + "java"
    elif java_bin_dir:
        command = java_bin_dir + "/java"
    else:
        command = "java"

    expect_ok = asutil.expect_ok_closure()
    output = await expect_ok(
        cmd=[command, "-version"],
        desc="Failed getting Java version",
        cwd=".",
        stdout=stdout_options["text"],
        stderr=stderr_options["stdout"],
        print_cmd=True,
    )
    logger.info(output)


async def generate_user_context():
    """ For now, returns a string of key:value,key:value """
    current_task = asyncio.Task.current_task()
    return "log-user-id:{},log-request-context:{},log-process-context:{},log-expires:{},log-tmp:{}".format(
        current_task.mdc["userId"],
        current_task.mdc["requestContext"],
        current_task.mdc["processContext"],
        current_task.mdc["expires"],
        current_task.mdc["tmp"],
    )
