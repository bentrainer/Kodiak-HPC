#!/usr/bin/env python3

import argparse
import copy
import getpass
import logging
import json
import re
import shutil
import subprocess
import time

from dataclasses import dataclass


@dataclass
class Queue:
    name: str
    pcpus: int
    avail_ncpus: int

@dataclass
class Job:
    id: str
    name: str
    owner: str
    queue: str
    state: str
    ncpus: int

@dataclass
class QueueRecord:
    njobq: int # number of jobs in Q state
    pcpus: int # total cpu count?
    ncpus: int # available cpu count
    waiting_jobs: list[Job]
    recv_jobs: list[Job]


__QSTAT__ = shutil.which("qstat")
__QMOVE__ = shutil.which("qmove")
__PBSND__ = shutil.which("pbsnodes")


def safe_json_str(content: str) -> str:
    return re.sub(r"([\[:,])(\s*)(-?)(\.\d+)", r"\g<1>\g<2>\g<3>0\g<4>", content)


def get_queue_info(queues: list[str], dry_run: bool=False) -> dict[str, Queue]:
    queue_info: dict[str, Queue] = {}
    cmdl = [__PBSND__ if __PBSND__ else "pbsnodes", "-a", "-F", "json"]

    for queue in queues:
        queue_info[queue] = Queue(queue, 0, 0)

    if dry_run:
        logging.info("dry run: " + " ".join(cmdl))
    else:
        sp = subprocess.run(cmdl, capture_output=True, check=True, text=True)
        pbs_info = json.loads(safe_json_str(sp.stdout))

        logging.debug(safe_json_str(sp.stdout))

        for _, info in (pbs_info["nodes"]).items():
            if info["queue"] in queues and "pcpus" in info:
                queue_info[info["queue"]].pcpus += info["pcpus"]

                avail_ncpus = 0
                try:
                    avail_ncpus = info["resources_available"]["ncpus"] - info["resources_assigned"]["ncpus"]
                except Exception:
                    pass
                finally:
                    queue_info[info["queue"]].avail_ncpus += avail_ncpus

    for _, q in queue_info.items():
        logging.debug(q)

    return queue_info


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GreedyBear - Periodically balances a user's queued jobs across specified PBS queues.",
    )

    username = getpass.getuser()

    parser.add_argument(
        "-u", "--user",
        type=str,
        help=f"User whose jobs to monitor. Defaults to the current user: {username}.",
        default=username,
    )
    parser.add_argument(
        "-q", "--queue",
        action="append",
        required=True,
        help="Queue to watch. This option can be specified multiple times (e.g., -q q1 -q q2).",
    )
    parser.add_argument(
        "-t", "--interval",
        type=int,
        default=60,
        help="Interval in seconds to check job status (default: 60).",
    )
    parser.add_argument(
        "-s", "--scheduler",
        type=str,
        default="balance",
        choices=["balance"],
        help="Scheduling strategy to use (default: balance).",
    )
    parser.add_argument(
        "-l", "--log",
        type=str,
        default="info",
        choices=["info", "debug", "error", "critical"],
        help="log level",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without actually moving jobs.",
    )

    args = parser.parse_args()

    args.queue = list(dict.fromkeys(args.queue))

    logging.basicConfig(
        format="[%(levelname)-4.4s][%(asctime)s] %(message)s",
        level=getattr(logging, args.log.upper(), logging.DEBUG),
    )

    global __QSTAT__
    global __QMOVE__

    if not __QSTAT__:
        logging.warning("qstat not found")
    if not __QMOVE__:
        logging.warning("qmove not found")
    if not __PBSND__:
        logging.error("pbsnodes not found")
    if args.dry_run:
        logging.info("dry run mode")

    args.queue_info = get_queue_info(args.queue, args.dry_run or not __PBSND__)

    return args


def get_user_jobs(args: argparse.Namespace) -> list[Job]:

    jobs = []
    cmdl = [__QSTAT__ if __QSTAT__ else "qstat", "-f", "-F", "json"]

    if not __QSTAT__:
        logging.info(f"qstat not found: {' '.join(cmdl)}")
    else:
        sp = subprocess.run(
            cmdl,
            capture_output=True,
            text=True,
            check=False
        )
        if sp.returncode:
            logging.warning(sp.stderr)
        else:
            try:
                resp = json.loads(safe_json_str(sp.stdout))
            except Exception as e:
                resp = {}
                logging.error(f"failed to parse json: {e}")

            jd = resp.get("Jobs", {})
            for k, v in jd.items():
                if v.get("Job_Owner", "").startswith(args.user):
                    jobs.append(Job(
                        id=k,
                        name=v.get("Job_Name", "unknown"),
                        owner=v.get("Job_Owner", "unknown"),
                        queue=v.get("queue", None),
                        state=v.get("job_state", "?"),
                        ncpus=(v.get("Resource_List", {})).get("ncpus", 1),
                    ))

    return jobs


def move_jobs_to_queue(jobs: list[Job], dest: str, dry_run: bool=False) -> None:
    for job in jobs:
        cmdl = [__QMOVE__ if __QMOVE__ else "qmove", dest, job.id]
        if dry_run:
            logging.info(f"dry run: {' '.join(cmdl)}")
        else:
            sp = subprocess.run(
                cmdl,
                capture_output=True,
                text=True,
                check=False,
            )
            if sp.returncode:
                logging.error(f"failed to move job: {sp.stdout}\n{sp.stderr}")


def scheduler_balance(jobs: list[Job], args: argparse.Namespace) -> None:

    args.queue_info = get_queue_info(args.queue, args.dry_run or not __PBSND__)

    jobs = [job for job in jobs if job.queue in args.queue]

    records: dict[str, QueueRecord] = {}
    for queue in args.queue:
        records[queue] = QueueRecord(
            njobq=0,
            pcpus=args.queue_info[queue].pcpus,
            ncpus=args.queue_info[queue].avail_ncpus,
            waiting_jobs=[],
            recv_jobs=[],
        )

    for job in jobs:
        if job.state=="R":
            if job.queue in records:
                records[job.queue].pcpus -= job.ncpus

    waiting_jobs = [job for job in jobs if job.state=="Q" and job.queue in args.queue and args.user in job.owner]
    waiting_jobs.sort(key=lambda x: x.ncpus)

    for qn, _ in records.items():
        for i in range(len(waiting_jobs)-1, -1, -1):
            if waiting_jobs[i].ncpus<=records[qn].ncpus:
                job = waiting_jobs.pop(i)
                records[qn].ncpus -= job.ncpus
                records[qn].recv_jobs.append(job)

    for job in waiting_jobs:
        records[job.queue].njobq += 1
        records[job.queue].waiting_jobs.append(job)


    donor = []
    n_target = len(waiting_jobs) // len(args.queue)

    for queue in args.queue: logging.info(f"found {records[queue].njobq} jobs waiting in queue: \"{queue}\"")
    logging.debug(f"total {len(waiting_jobs)} waiting jobs, expected at least {n_target} for each queue")


    for k, v in records.items():
        if v.njobq > n_target + 1:
            d_jobs = v.waiting_jobs[(n_target-v.njobq):]
            donor += d_jobs
            logging.debug(f"{k} queue gives away {len(d_jobs)} jobs")

    for k, v in records.items():
        if v.njobq < n_target:
            diff = min(n_target-v.njobq, len(donor))
            records[k].recv_jobs += donor[:diff]
            donor = donor[diff:]
            logging.debug(f"{k} queue takes {diff} jobs from donor list")

    if donor:
        pos = 0
        logging.debug(f"{len(donor)} jobs left, round robin")
        while donor:
            # round-robin
            records[args.queue[pos]].recv_jobs.append(donor.pop())
            pos = (pos+1) % len(args.queue)


    mvdflag = False
    for qname, v in records.items():
        mjobs = v.recv_jobs
        mjobs = [job for job in mjobs if job.queue!=qname]
        if mjobs:
            logging.info(f"moving {len(mjobs)} jobs to queue \"{qname}\"...")
            mvdflag = True
            move_jobs_to_queue(
                jobs=mjobs,
                dest=qname,
                dry_run=(args.dry_run or __QMOVE__ is None),
            )

    if not mvdflag:
        logging.info("no need for moving")

    # for k, v in records.items():
    #     n_move = len(v.recv_jobs)
    #     if n_move:
    #         logging.info(f"moving {n_move} jobs to queue \"{k}\"...")
    #         move_jobs_to_queue(
    #             jobs=v.recv_jobs,
    #             dest=k,
    #             dry_run=(args.dry_run or __QMOVE__ is None),
    #         )


def main() -> None:
    args = parse_arguments()

    try:
        logging.info("start monitoring queue(s): " + " ".join(args.queue))
        for queue, info in args.queue_info.items():
            logging.info(f"found {info.pcpus} cpu(s) configured in \"{queue}\" queue")

        while True:
            jobs = get_user_jobs(args)

            logging.debug("get jobs:")
            for job in jobs:
                logging.debug(job)

            match args.scheduler:
                case "balance":
                    scheduler_balance(jobs, args)
                case _:
                    logging.warning(f"\"{args.scheduler}\" not implemented")
                    raise KeyboardInterrupt()

            logging.info(f"sleep {args.interval}s...")
            time.sleep(args.interval)

    except KeyboardInterrupt:
        logging.info("GreedyBear interrupted, exiting...")
    except Exception as e:
        logging.critical(f"unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logging.info("Bye~")

if __name__ == "__main__":
    main()
