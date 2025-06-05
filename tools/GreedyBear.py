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
    pcpus: int
    waiting_jobs: list[Job]
    recv_jobs: list[Job]


__QSTAT__ = shutil.which("qstat")
__QMOVE__ = shutil.which("qmove")
__PBSND__ = shutil.which("pbsnodes")


def safe_json_str(content: str) -> str:
    return re.sub(r"([\[:,])(\s*)(-?)(\.\d+)", r"\g<1>\g<2>\g<3>0\g<4>", content)


def get_queue_info(queues: list[str], dry_run: bool=False) -> dict[str, Queue]:
    queue_info = {}
    cmdl = [__PBSND__ if __PBSND__ else "pbsnodes", "-a", "-F", "json"]

    for queue in queues:
        queue_info[queue] = Queue(queue, 0)

    if dry_run:
        logging.info("dry run: " + " ".join(cmdl))
    else:
        sp = subprocess.run(cmdl, capture_output=True, check=True, text=True)
        pbs_info = json.loads(safe_json_str(sp.stdout))

        for _, info in (pbs_info["nodes"]).items():
            if info["queue"] in queues:
                queue_info[info["queue"]].pcpus += info["pcpus"]

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


class HungarianAlgorithm:
    """
    Implementation of the Hungarian Algorithm for the assignment problem.
    """
    def __init__(self, cost_matrix):
        self.cost_matrix = copy.deepcopy(cost_matrix)
        self.n = len(cost_matrix)
        self.m = len(cost_matrix[0])
        self.row_covered = [False] * self.n
        self.col_covered = [False] * self.m
        self.zeros_pos = []
        self.path = []
        self.marked = [[0] * self.m for _ in range(self.n)]

    def _find_a_zero(self):
        for i in range(self.n):
            for j in range(self.m):
                if self.cost_matrix[i][j] == 0 and not self.row_covered[i] and not self.col_covered[j]:
                    return i, j
        return -1, -1

    def _find_star_in_row(self, row):
        for j in range(self.m):
            if self.marked[row][j] == 1:
                return j
        return -1

    def _find_star_in_col(self, col):
        for i in range(self.n):
            if self.marked[i][col] == 1:
                return i
        return -1

    def _find_prime_in_row(self, row):
        for j in range(self.m):
            if self.marked[row][j] == 2:
                return j
        return -1

    def _clear_covers(self):
        self.row_covered = [False] * self.n
        self.col_covered = [False] * self.m

    def _step1(self):
        for i in range(self.n):
            min_val = min(self.cost_matrix[i])
            for j in range(self.m):
                self.cost_matrix[i][j] -= min_val

    def _step2(self):
        for j in range(self.m):
            min_val = min(self.cost_matrix[i][j] for i in range(self.n))
            for i in range(self.n):
                self.cost_matrix[i][j] -= min_val

    def _step3(self):
        for i in range(self.n):
            for j in range(self.m):
                if self.cost_matrix[i][j] == 0:
                    col_has_star = False
                    for row in range(self.n):
                        if self.marked[row][j] == 1:
                            col_has_star = True
                            break
                    if not col_has_star:
                        self.marked[i][j] = 1
                        break
        return 4

    def _step4(self):
        star_count = 0
        for j in range(self.m):
            for i in range(self.n):
                if self.marked[i][j] == 1:
                    self.col_covered[j] = True
                    star_count += 1
        return 5 if star_count >= self.n else 6

    def _step5(self):
        while True:
            row, col = self._find_a_zero()
            if row == -1:
                return 7
            self.marked[row][col] = 2
            star_col = self._find_star_in_row(row)
            if star_col != -1:
                self.row_covered[row] = True
                self.col_covered[star_col] = False
            else:
                self.path = [(row, col)]
                return 6

    def _step6(self):
        while True:
            last_row, last_col = self.path[-1]
            star_row = self._find_star_in_col(last_col)
            if star_row == -1:
                break
            self.path.append((star_row, last_col))
            prime_col = self._find_prime_in_row(star_row)
            self.path.append((star_row, prime_col))

        for r, c in self.path:
            if self.marked[r][c] == 1:
                self.marked[r][c] = 0
            elif self.marked[r][c] == 2:
                self.marked[r][c] = 1

        self._clear_covers()
        for i in range(self.n):
            for j in range(self.m):
                if self.marked[i][j] == 2:
                    self.marked[i][j] = 0
        return 4

    def _step7(self):
        min_uncovered = float('inf')
        for i in range(self.n):
            if not self.row_covered[i]:
                for j in range(self.m):
                    if not self.col_covered[j]:
                        if self.cost_matrix[i][j] < min_uncovered:
                            min_uncovered = self.cost_matrix[i][j]

        for i in range(self.n):
            for j in range(self.m):
                if self.row_covered[i]:
                    self.cost_matrix[i][j] += min_uncovered
                if not self.col_covered[j]:
                    self.cost_matrix[i][j] -= min_uncovered
        return 5

    def solve(self):
        self._step1()
        self._step2()

        step = 3
        while step is not None:
            if step == 3:
                step = self._step3()
            elif step == 4:
                step = self._step4()
            elif step == 5:
                step = self._step5()
            elif step == 6:
                step = self._step6()
            elif step == 7:
                step = self._step7()

            if step == 5 and sum(self.col_covered) >= self.n:
                break

        results = []
        for i in range(self.n):
            for j in range(self.m):
                if self.marked[i][j] == 1:
                    results.append((i, j))
        return results


def minimize_mismatches(lists_of_elements: list[list[Job]], list_names: list[str]) -> list[list[Job]]:
    """
    Rearranges elements across lists to minimize mismatches without third-party libraries.
    """
    all_elements = [element for sublist in lists_of_elements for element in sublist]

    slots = []
    for i, sublist in enumerate(lists_of_elements):
        slots.extend([list_names[i]] * len(sublist))

    num_elements = len(all_elements)
    if num_elements==0:
        return lists_of_elements

    # Build the cost matrix
    cost_matrix = [[0] * num_elements for _ in range(num_elements)]
    for i, element in enumerate(all_elements):
        for j, slot_queue in enumerate(slots):
            if element.queue != slot_queue:
                cost_matrix[i][j] = 1

    # Solve using the Hungarian Algorithm
    solver = HungarianAlgorithm(cost_matrix)
    assignment = solver.solve()

    # Reconstruct the new lists
    temp_new_lists = {name: [] for name in list_names}

    slot_to_list_map = []
    for name, sublist in zip(list_names, lists_of_elements):
        slot_to_list_map.extend([name] * len(sublist))

    for row, col in assignment:
        element = all_elements[row]
        target_list_name = slot_to_list_map[col]
        temp_new_lists[target_list_name].append(element)

    final_new_lists = [temp_new_lists[name] for name in list_names]

    return final_new_lists


def scheduler_balance(jobs: list[Job], args: argparse.Namespace) -> None:

    jobs = [job for job in jobs if job.queue in args.queue]

    records = {}
    for queue in args.queue:
        records[queue] = QueueRecord(
            njobq=0,
            pcpus=args.queue_info[queue].pcpus,
            waiting_jobs=[],
            recv_jobs=[],
        )

    for job in jobs:
        if job.state=="R":
            if job.queue in records:
                records[job.queue].pcpus -= job.ncpus

    waiting_jobs = [job for job in jobs if job.state=="Q"]
    logging.info(f"found {len(waiting_jobs)} jobs waiting in queue(s): \"" + "\", \"".join(args.queue)+"\"")

    waiting_jobs.sort(key=lambda x: x.ncpus)

    for k, v in records.items():
        for i in range(len(waiting_jobs)-1, -1, -1):
            if waiting_jobs[i].ncpus<=v.pcpus:
                job = waiting_jobs.pop(i)
                records[k].pcpus -= job.ncpus
                records[k].recv_jobs.append(job)

    donor = []
    n_target = len(waiting_jobs) // len(args.queue)

    for job in waiting_jobs:
        if job.queue in records:
            records[job.queue].njobq += 1
            records[job.queue].waiting_jobs.append(job)

    for _, v in records.items():
        if v.njobq > n_target:
            donor += v["jobs"][:(n_target-v.njobq)]

    for k, v in records.items():
        if v.njobq < n_target:
            diff = min(n_target-v.njobq, len(donor))
            records[k].recv_jobs += donor[:diff]
            donor = donor[diff:]

    if donor:
        pos = 0
        while donor:
            # round-robin
            records[args.queue[pos]].append(donor.pop())
            pos = (pos+1) % len(args.queue)

    mmlists = []
    mmnames = []
    for k, v in records.items():
        mmlists.append(v.recv_jobs)
        mmnames.append(k)

    # rearrange the moving lists, so that the moving steps are minimized
    # minimize_mismatches & HungarianAlgorithm generated by Gemini 2.5 Pro
    mmlists = minimize_mismatches(mmlists, mmnames)
    mvdflag = False
    for qname, mjobs in zip(mmnames, mmlists):
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
