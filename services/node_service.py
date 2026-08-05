import os
import shutil
import uuid
from datetime import datetime, timezone, timedelta

class NodeService:
    def __init__(self, conn, cursor):
        self.conn = conn
        self.cursor = cursor

    def register_node(self, node):
        now = datetime.now(timezone.utc).isoformat()

        self.cursor.execute("""
            INSERT INTO nodes
            (node_id, country, storage_gb, status, last_seen)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (node_id)
            DO UPDATE SET
                country = EXCLUDED.country,
                storage_gb = EXCLUDED.storage_gb,
                status = EXCLUDED.status,
                last_seen = EXCLUDED.last_seen
        """, (
            node.node_id,
            node.country,
            node.storage_gb,
            node.status,
            now
        ))

        self.conn.commit()

        self.cursor.execute("SELECT COUNT(*) FROM nodes")
        total_nodes = self.cursor.fetchone()[0]

        return {
            "success": True,
            "node_id": node.node_id,
            "total_nodes": total_nodes,
            "last_seen": now,
            "message": "Node registered successfully"
        }

    def get_node(self, node_id):
        self.cursor.execute("""
            SELECT node_id, country, storage_gb, status, last_seen
            FROM nodes
            WHERE node_id = %s
        """, (node_id,))

        row = self.cursor.fetchone()

        if not row:
            return {
                "success": False,
                "message": "Node not found",
                "node_id": node_id
            }

        return {
            "success": True,
            "node_id": row[0],
            "country": row[1],
            "storage_gb": row[2],
            "status": row[3],
            "last_seen": row[4]
        }

    def heartbeat(self, heartbeat):
        now = datetime.now(timezone.utc).isoformat()

        self.cursor.execute("""
            UPDATE nodes
            SET status = %s,
                last_seen = %s
            WHERE node_id = %s
        """, (
            heartbeat.status,
            now,
            heartbeat.node_id
        ))

        self.conn.commit()

        if self.cursor.rowcount == 0:
            return {
                "success": False,
                "message": "Node not found"
            }

        return {
            "success": True,
            "node_id": heartbeat.node_id,
            "status": heartbeat.status,
            "last_seen": now,
            "message": "Heartbeat received"
        }

    def get_online_nodes(self):
        now = datetime.now(timezone.utc)

        self.cursor.execute("""
            SELECT node_id, country, storage_gb, status, last_seen
            FROM nodes
        """)

        rows = self.cursor.fetchall()
        online_list = []

        for row in rows:
            if row[4] is None:
                continue

            last_seen = row[4]
            if isinstance(last_seen, str):
                last_seen = datetime.fromisoformat(last_seen)

            minutes_since_seen = (now - last_seen).total_seconds() / 60

            if minutes_since_seen <= 5:
                online_list.append({
                    "node_id": row[0],
                    "country": row[1],
                    "storage_gb": row[2],
                    "status": "online",
                    "last_seen": row[4],
                    "minutes_since_seen": round(minutes_since_seen, 2)
                })

        return {
            "total_online_nodes": len(online_list),
            "nodes": online_list
        }

    def get_offline_nodes(self):
        now = datetime.now(timezone.utc)

        self.cursor.execute("""
            SELECT node_id, country, storage_gb, status, last_seen
            FROM nodes
        """)

        rows = self.cursor.fetchall()
        offline_list = []

        for row in rows:
            if row[4] is None:
                offline_list.append({
                    "node_id": row[0],
                    "country": row[1],
                    "storage_gb": row[2],
                    "status": "offline",
                    "last_seen": None,
                    "minutes_since_seen": None
                })
                continue

            last_seen = row[4]
            if isinstance(last_seen, str):
                last_seen = datetime.fromisoformat(last_seen)

            minutes_since_seen = (now - last_seen).total_seconds() / 60

            if minutes_since_seen > 5:
                offline_list.append({
                    "node_id": row[0],
                    "country": row[1],
                    "storage_gb": row[2],
                    "status": "offline",
                    "last_seen": row[4],
                    "minutes_since_seen": round(minutes_since_seen, 2)
                })

        return {
            "total_offline_nodes": len(offline_list),
            "nodes": offline_list
        }

    def get_network_capacity(self):
        self.cursor.execute("""
            SELECT storage_gb, status
            FROM nodes
        """)

        rows = self.cursor.fetchall()

        total_storage = 0
        online_storage = 0
        offline_storage = 0

        total_nodes = len(rows)
        online_nodes = 0
        offline_nodes = 0

        for row in rows:
            storage = row[0]
            status = row[1]

            total_storage += storage

            if status == "online":
                online_storage += storage
                online_nodes += 1
            else:
                offline_storage += storage
                offline_nodes += 1

        return {
            "total_nodes": total_nodes,
            "online_nodes": online_nodes,
            "offline_nodes": offline_nodes,
            "total_storage_gb": total_storage,
            "online_storage_gb": online_storage,
            "offline_storage_gb": offline_storage
        }

    def allocate_storage(self, request):
        self.cursor.execute("""
            SELECT node_id, storage_gb, status
            FROM nodes
            WHERE status = 'online'
        """)

        rows = self.cursor.fetchall()

        if not rows:
            return {
                "success": False,
                "message": "No online nodes available"
            }

        selected_node = rows[0]
        allocation_id = "ALLOC-" + str(uuid.uuid4())
        allocated_at = datetime.now(timezone.utc).isoformat()

        self.cursor.execute("""
            INSERT INTO allocations
            (allocation_id, node_id, file_size_gb, allocated_at, status)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            allocation_id,
            selected_node[0],
            request.file_size_gb,
            allocated_at,
            "active"
        ))

        self.conn.commit()

        return {
            "success": True,
            "allocation_id": allocation_id,
            "selected_node": selected_node[0],
            "file_size_gb": request.file_size_gb,
            "allocated_at": allocated_at,
            "status": "active",
            "message": "Storage allocated successfully"
        }
    def select_best_node(self):
        self.cursor.execute("""
            SELECT
                n.node_id,
                COALESCE(su.available_storage_gb, 0) AS available_storage_gb,
                COALESCE(su.used_storage_gb, 0) AS used_storage_gb
            FROM nodes n
            LEFT JOIN node_storage_usage su
                ON n.node_id = su.node_id
            WHERE n.status = 'online'
            ORDER BY available_storage_gb DESC, used_storage_gb ASC
            LIMIT 1
        """)

        row = self.cursor.fetchone()

        if not row:
            return None

        return {
            "node_id": row[0],
            "available_storage_gb": row[1],
            "used_storage_gb": row[2]
        }

    def select_replica_nodes(self, primary_node_id, replica_count):
        self.cursor.execute("""
            SELECT
                n.node_id,
                COALESCE(su.available_storage_gb, 0) AS available_storage_gb
            FROM nodes n
            LEFT JOIN node_storage_usage su
                ON n.node_id = su.node_id
            WHERE n.status = 'online'
              AND n.node_id != %s
            ORDER BY available_storage_gb DESC, n.node_id ASC
            LIMIT %s
        """, (primary_node_id, replica_count))

        rows = self.cursor.fetchall()

        replica_nodes = []

        for row in rows:
            replica_nodes.append({
                "node_id": row[0],
                "available_storage_gb": row[1]
            })

        return replica_nodes

    def mark_node_offline(self, node_id):
        created_at = datetime.now(timezone.utc).isoformat()

        self.cursor.execute("""
            SELECT status
            FROM nodes
            WHERE node_id = %s
        """, (node_id,))

        row = self.cursor.fetchone()

        if not row:
            return {
                "success": False,
                "message": "Node not found",
                "node_id": node_id
            }

        previous_status = row[0]

        self.cursor.execute("""
            UPDATE nodes
            SET status = %s,
                last_seen = %s
            WHERE node_id = %s
        """, (
            "offline",
            created_at,
            node_id
        ))

        health_event_id = "HEALTH-" + str(uuid.uuid4())

        self.cursor.execute("""
            INSERT INTO node_health_events
            (event_id, node_id, health_status, created_at)
            VALUES (%s, %s, %s, %s)
        """, (
            health_event_id,
            node_id,
            "offline",
            created_at
        ))

        self.conn.commit()

        return {
            "success": True,
            "node_id": node_id,
            "previous_status": previous_status,
            "new_status": "offline",
            "health_event_id": health_event_id,
            "message": "Node marked offline"
        }

    def mark_node_online(self, node_id):
        created_at = datetime.now(timezone.utc).isoformat()

        self.cursor.execute("""
            SELECT status
            FROM nodes
            WHERE node_id = %s
        """, (node_id,))

        row = self.cursor.fetchone()

        if not row:
            return {
                "success": False,
                "message": "Node not found",
                "node_id": node_id
            }

        previous_status = row[0]

        self.cursor.execute("""
            UPDATE nodes
            SET status = %s,
                last_seen = %s
            WHERE node_id = %s
        """, (
            "online",
            created_at,
            node_id
        ))

        health_event_id = "HEALTH-" + str(uuid.uuid4())

        self.cursor.execute("""
            INSERT INTO node_health_events
            (event_id, node_id, health_status, created_at)
            VALUES (%s, %s, %s, %s)
        """, (
            health_event_id,
            node_id,
            "online",
            created_at
        ))

        self.conn.commit()

        return {
            "success": True,
            "node_id": node_id,
            "previous_status": previous_status,
            "new_status": "online",
            "health_event_id": health_event_id,
            "message": "Node marked online"
        }

    def recover_node(self, node_id):
        created_at = datetime.now(timezone.utc).isoformat()

        self.cursor.execute("""
            SELECT status
            FROM nodes
            WHERE node_id = %s
        """, (node_id,))

        row = self.cursor.fetchone()

        if not row:
            return {
                "success": False,
                "message": "Node not found",
                "node_id": node_id
            }

        previous_status = row[0]

        self.cursor.execute("""
            UPDATE nodes
            SET status = %s,
                last_seen = %s
            WHERE node_id = %s
        """, (
            "online",
            created_at,
            node_id
        ))

        event_id = "HEALTH-" + str(uuid.uuid4())

        self.cursor.execute("""
            INSERT INTO node_health_events
            (event_id, node_id, health_status, created_at)
            VALUES (%s, %s, %s, %s)
        """, (
            event_id,
            node_id,
            "recovered",
            created_at
        ))

        self.conn.commit()

        return {
            "success": True,
            "node_id": node_id,
            "previous_status": previous_status,
            "new_status": "online",
            "health_event_id": event_id,
            "message": "Node recovered successfully"
        }

    def get_node_chunks(self, node_id):
        self.cursor.execute("""
            SELECT storage_id,
                   file_id,
                   chunk_id,
                   node_id,
                   chunk_path,
                   chunk_size_bytes,
                   storage_type,
                   status,
                   created_at
            FROM distributed_chunk_storage
            WHERE node_id = %s
            ORDER BY created_at DESC
        """, (node_id,))

        rows = self.cursor.fetchall()

        records = []

        for row in rows:
            records.append({
                "storage_id": row[0],
                "file_id": row[1],
                "chunk_id": row[2],
                "node_id": row[3],
                "chunk_path": row[4],
                "chunk_size_bytes": row[5],
                "storage_type": row[6],
                "status": row[7],
                "created_at": row[8]
            })

        return {
            "node_id": node_id,
            "total_chunks": len(records),
            "chunks": records
        }

    def get_node_impact(self, node_id):
        return self.get_node_chunks(node_id)

    def simulate_node_failure(self, node_id):
        mark_result = self.mark_node_offline(node_id)

        if not mark_result.get("success"):
            return mark_result

        impact_result = self.get_node_impact(node_id)

        return {
            "success": True,
            "node_id": node_id,
            "previous_status": mark_result.get("previous_status"),
            "new_status": mark_result.get("new_status"),
            "health_event_id": mark_result.get("health_event_id"),
            "total_impacted_chunks": impact_result.get("total_chunks", 0),
            "impacted_chunks": impact_result.get("chunks", []),
            "message": "Node failure simulated"
        }

    def get_node_health_events(self):
        self.cursor.execute("""
            SELECT event_id, node_id, health_status, created_at
            FROM node_health_events
            ORDER BY created_at DESC
        """)

        rows = self.cursor.fetchall()

        events = []

        for row in rows:
            events.append({
                "event_id": row[0],
                "node_id": row[1],
                "health_status": row[2],
                "created_at": row[3]
            })

        return {
            "total_events": len(events),
            "events": events
        }

    def automatic_failover(self, node_id):
        created_at = datetime.now(timezone.utc).isoformat()

        # Confirm that the failed node exists.
        self.cursor.execute(
            """
            SELECT status
            FROM nodes
            WHERE node_id = %s
            """,
            (node_id,)
        )

        node_row = self.cursor.fetchone()

        if not node_row:
            return {
                "success": False,
                "message": "Node not found",
                "node_id": node_id
            }

        previous_status = node_row[0]

        # Mark the failed node offline.
        self.cursor.execute(
            """
            UPDATE nodes
            SET status = %s,
                last_seen = %s
            WHERE node_id = %s
            """,
            ("offline", created_at, node_id)
        )

        # Mark the failed node offline.
        self.cursor.execute(
            """
            UPDATE nodes
            SET status = %s,
                last_seen = %s
            WHERE node_id = %s
            """,
            ("offline", created_at, node_id)
        )

        # Mark every active replica on the failed node as failed.
        self.cursor.execute(
            """
            UPDATE distributed_chunk_replicas
            SET status = 'failed'
            WHERE replica_node_id = %s
              AND status IN ('replicated', 'promoted_to_primary')
            """,
            (node_id,)
         )

        # Find all active primary chunks stored on the failed node.
        self.cursor.execute(
            """
            SELECT storage_id,
                   file_id,
                   chunk_id,
                   node_id,
                   chunk_path,
                   chunk_size_bytes
            FROM distributed_chunk_storage
            WHERE node_id = %s
              AND storage_type = 'primary'
              AND status = 'stored'
            ORDER BY file_id, chunk_id
            """,
            (node_id,)
        )

        affected_chunks = self.cursor.fetchall()

        failover_events = []
        rereplication_events = []

        for chunk in affected_chunks:
            storage_id = chunk[0]
            file_id = chunk[1]
            chunk_id = chunk[2]
            failed_node_id = chunk[3]
            chunk_path = chunk[4]
            chunk_size_bytes = chunk[5]

            # Find an existing healthy replica on an online node.
            self.cursor.execute(
                """
                SELECT dcr.replica_id,
                       dcr.replica_node_id,
                       dcr.chunk_path,
                       dcr.chunk_size_bytes
                FROM distributed_chunk_replicas dcr
                JOIN nodes n
                  ON n.node_id = dcr.replica_node_id
                WHERE dcr.file_id = %s
                  AND dcr.chunk_id = %s
                  AND dcr.status = 'replicated'
                  AND dcr.replica_node_id <> %s
                  AND n.status = 'online'
                ORDER BY dcr.replica_number ASC
                LIMIT 1
                """,
                (file_id, chunk_id, failed_node_id)
            )

            replica_row = self.cursor.fetchone()

            if not replica_row:
                failover_events.append({
                    "file_id": file_id,
                    "chunk_id": chunk_id,
                    "failed_node_id": failed_node_id,
                    "status": "no_replica_available"
                })
                continue

            promoted_replica_id = replica_row[0]
            promoted_node_id = replica_row[1]
            promoted_chunk_path = replica_row[2]
            promoted_chunk_size_bytes = replica_row[3]

            # Mark the old primary record as failed.
            self.cursor.execute(
                """
                UPDATE distributed_chunk_storage
                SET status = 'failed'
                WHERE storage_id = %s
                """,
                (storage_id,)
            )

            # Clear any previous promoted replica for this chunk.
            self.cursor.execute(
                """
                UPDATE distributed_chunk_replicas
                SET status = 'replicated'
                WHERE file_id = %s
                  AND chunk_id = %s
                  AND status = 'promoted_to_primary'
                """,
                (file_id, chunk_id)
            )

            # Mark the selected replica as promoted.
            self.cursor.execute(
                """
                UPDATE distributed_chunk_replicas
                SET status = 'promoted_to_primary'
                WHERE replica_id = %s
                """,
                (promoted_replica_id,)
            )

            # Create a new primary storage record for the promoted replica.
            promoted_storage_id = "DSTORAGE-" + str(uuid.uuid4())

            self.cursor.execute(
                """
                INSERT INTO distributed_chunk_storage
                (
                    storage_id,
                    file_id,
                    chunk_id,
                    node_id,
                    chunk_path,
                    chunk_size_bytes,
                    storage_type,
                    status,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    promoted_storage_id,
                    file_id,
                    chunk_id,
                    promoted_node_id,
                    promoted_chunk_path,
                    promoted_chunk_size_bytes,
                    "primary",
                    "stored",
                    created_at
                )
            )

            # Record the primary-promotion recovery event.
            recovery_id = "RECOVERY-" + str(uuid.uuid4())

            self.cursor.execute(
                """
                INSERT INTO recovery_events
                (
                    recovery_id,
                    file_id,
                    chunk_id,
                    failed_node_id,
                    promoted_node_id,
                    recovery_action,
                    status,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    recovery_id,
                    file_id,
                    chunk_id,
                    failed_node_id,
                    promoted_node_id,
                    "automatic_failover",
                    "recovered",
                    created_at
                )
            )

            failover_events.append({
                "recovery_id": recovery_id,
                "file_id": file_id,
                "chunk_id": chunk_id,
                "failed_node_id": failed_node_id,
                "promoted_node_id": promoted_node_id,
                "promoted_storage_id": promoted_storage_id,
                "status": "recovered"
            })

            # Find every node already holding this chunk.
            self.cursor.execute(
                """
                SELECT node_id
                FROM distributed_chunk_storage
                WHERE file_id = %s
                  AND chunk_id = %s
                  AND status = 'stored'

                UNION 


                SELECT replica_node_id
                FROM distributed_chunk_replicas
                WHERE file_id = %s
                  AND chunk_id = %s
                  AND status IN ('replicated', 'promoted_to_primary')
                """,
                (file_id, chunk_id, file_id, chunk_id)
            )

            existing_node_ids = {
                row[0] for row in self.cursor.fetchall()
            }

            existing_node_ids.add(failed_node_id)
            existing_node_ids.add(promoted_node_id)

            # Choose an online node that does not already hold this chunk.
            self.cursor.execute(
                """
                SELECT node_id
                FROM nodes
                WHERE status = 'online'
                ORDER BY node_id
                """
            )

            candidate_nodes = [
                row[0]
                for row in self.cursor.fetchall()
                if row[0] not in existing_node_ids
            ]

            if not candidate_nodes:
                rereplication_events.append({
                    "file_id": file_id,
                    "chunk_id": chunk_id,
                    "promoted_node_id": promoted_node_id,
                    "status": "no_replacement_node_available"
                })
                continue

            replacement_node_id = candidate_nodes[0]
            replacement_replica_id = "DREPLICA-" + str(uuid.uuid4())

            # Determine the next replica number for this chunk.
            self.cursor.execute(
                """
                SELECT COALESCE(MAX(replica_number), 0)
                FROM distributed_chunk_replicas
                WHERE file_id = %s
                  AND chunk_id = %s
                """,
                (file_id, chunk_id)
            )

            next_replica_number = self.cursor.fetchone()[0] + 1

            # Add the replacement replica.
            #
            # In the current single-server prototype, chunk_path references the
            # existing physical chunk file. When real node agents are introduced,
            # this section will perform an actual network copy to the new node.
            self.cursor.execute(
                """
                INSERT INTO distributed_chunk_replicas
                (
                    replica_id,
                    file_id,
                    chunk_id,
                    primary_node_id,
                    replica_node_id,
                    chunk_path,
                    chunk_size_bytes,
                    replica_number,
                    status,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    replacement_replica_id,
                    file_id,
                    chunk_id,
                    promoted_node_id,
                    replacement_node_id,
                    promoted_chunk_path,
                    promoted_chunk_size_bytes,
                    next_replica_number,
                    "replicated",
                    created_at
                )
            )

            chunk_size_gb = promoted_chunk_size_bytes / (1024 * 1024 * 1024)

            # Update replacement-node storage accounting.
            self.cursor.execute(
                """
                UPDATE node_storage_usage
                SET used_storage_gb = used_storage_gb + %s,
                    available_storage_gb = available_storage_gb - %s,
                    last_updated = %s
                WHERE node_id = %s
                """,
                (
                    chunk_size_gb,
                    chunk_size_gb,
                    created_at,
                    replacement_node_id
                )
            )

            rereplication_recovery_id = "RECOVERY-" + str(uuid.uuid4())

            self.cursor.execute(
                """
                INSERT INTO recovery_events
                (
                    recovery_id,
                    file_id,
                    chunk_id,
                    failed_node_id,
                    promoted_node_id,
                    recovery_action,
                    status,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    rereplication_recovery_id,
                    file_id,
                    chunk_id,
                    failed_node_id,
                    replacement_node_id,
                    "automatic_rereplication",
                    "replicated",
                    created_at
                )
            )

            rereplication_events.append({
                "recovery_id": rereplication_recovery_id,
                "file_id": file_id,
                "chunk_id": chunk_id,
                "primary_node_id": promoted_node_id,
                "replacement_replica_node_id": replacement_node_id,
                "replacement_replica_id": replacement_replica_id,
                "replica_number": next_replica_number,
                "status": "replicated"
            })

        self.conn.commit()

        return {
            "success": True,
            "failed_node_id": node_id,
            "previous_status": previous_status,
            "new_status": "offline",
            "affected_primary_chunks": len(affected_chunks),
            "failover_events_created": len(failover_events),
            "rereplication_events_created": len(rereplication_events),
            "failover_events": failover_events,
            "rereplication_events": rereplication_events
        }

    def system_health(self):
        self.cursor.execute("SELECT COUNT(*) FROM nodes")
        total_nodes = self.cursor.fetchone()[0]

        self.cursor.execute("SELECT COUNT(*) FROM nodes WHERE status = 'online'")
        online_nodes = self.cursor.fetchone()[0]

        self.cursor.execute("SELECT COUNT(*) FROM nodes WHERE status = 'offline'")
        offline_nodes = self.cursor.fetchone()[0]

        self.cursor.execute("SELECT COUNT(*) FROM files")
        total_files = self.cursor.fetchone()[0]

        return {
            "success": True,
            "total_nodes": total_nodes,
            "online_nodes": online_nodes,
            "offline_nodes": offline_nodes,
            "total_files": total_files,
            "status": "healthy"
        }

    def network_summary(self):
        self.cursor.execute("""
            SELECT status, COUNT(*)
            FROM nodes
            GROUP BY status
            ORDER BY status
        """)
        rows = self.cursor.fetchall()

        summary = []
        for row in rows:
            summary.append({
                "status": row[0],
                "count": row[1]
            })

        return {
            "success": True,
            "network_summary": summary,
            "status": "network_summary_ready"
        }

    def node_report(self, node_id):
        self.cursor.execute("""
            SELECT node_id, country, storage_gb, status, last_seen
            FROM nodes
            WHERE node_id = %s
        """, (node_id,))
        node = self.cursor.fetchone()

        if not node:
            return {"success": False, "message": "Node not found", "node_id": node_id}

        self.cursor.execute("""
            SELECT COUNT(*)
            FROM distributed_chunk_storage
            WHERE node_id = %s
        """, (node_id,))
        chunk_count = self.cursor.fetchone()[0]

        return {
            "success": True,
            "node_id": node[0],
            "country": node[1],
            "storage_gb": node[2],
            "status": node[3],
            "last_seen": node[4],
            "stored_chunks": chunk_count
        }

    def node_storage(self, node_id):
        self.cursor.execute("""
            SELECT
                node_id,
                storage_gb,
                status
            FROM nodes
            WHERE node_id=%s
        """,(node_id,))

        node=self.cursor.fetchone()

        if not node:
            return {
                "success":False,
                "message":"Node not found"
            }

        self.cursor.execute("""
            SELECT
                COUNT(*),
                COALESCE(SUM(chunk_size_bytes),0)
            FROM distributed_chunk_storage
            WHERE node_id=%s
        """,(node_id,))

        stats=self.cursor.fetchone()

        return {
            "success":True,
            "node_id":node[0],
            "storage_gb":node[1],
            "status":node[2],
            "chunks":stats[0],
            "stored_bytes":stats[1]
        }

    def node_health_events(self):
        self.cursor.execute("""
            SELECT event_id, node_id, health_status, created_at
            FROM node_health_events
            ORDER BY created_at DESC
            LIMIT 20
        """)
        rows = self.cursor.fetchall()

        events = []
        for row in rows:
            events.append({
                "event_id": row[0],
                "node_id": row[1],
                "health_status": row[2],
                "created_at": row[3]
            })

        return {
            "success": True,
            "total_events": len(events),
            "events": events
        }

    def capacity_report(self):
        self.cursor.execute("""
            SELECT
                node_id,
                country,
                storage_gb,
                status
            FROM nodes
            ORDER BY storage_gb DESC
        """)

        rows = self.cursor.fetchall()

        report = []
        for row in rows:
            report.append({
                "node_id": row[0],
                "country": row[1],
                "storage_gb": row[2],
                "status": row[3]
            })

        return {
            "success": True,
            "nodes_reported": len(report),
            "capacity_report": report
        }

    def cluster_summary(self):
        self.cursor.execute("""
            SELECT COUNT(*)
            FROM nodes
        """)
        total_nodes = self.cursor.fetchone()[0]

        self.cursor.execute("""
            SELECT COUNT(*)
            FROM nodes
            WHERE status = 'online'
        """)
        online_nodes = self.cursor.fetchone()[0]

        self.cursor.execute("""
            SELECT COUNT(*)
            FROM nodes
            WHERE status = 'offline'
        """)
        offline_nodes = self.cursor.fetchone()[0]

        self.cursor.execute("""
            SELECT COALESCE(SUM(storage_gb), 0)
            FROM nodes
        """)
        total_storage_gb = self.cursor.fetchone()[0]

        return {
            "success": True,
            "total_nodes": total_nodes,
            "online_nodes": online_nodes,
            "offline_nodes": offline_nodes,
            "total_storage_gb": total_storage_gb,
            "status": "cluster_summary_ready"
        }

    def initialize_storage_usage(self):
        self.cursor.execute("""
            SELECT node_id, storage_gb
            FROM nodes
        """)

        nodes = self.cursor.fetchall()
        updated_at = datetime.now(timezone.utc).isoformat()
        initialized_nodes = []

        for node in nodes:
            self.cursor.execute("""
                INSERT INTO node_storage_usage
                (node_id, total_storage_gb, used_storage_gb, available_storage_gb, last_updated)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (node_id)
                DO UPDATE SET
                    total_storage_gb = EXCLUDED.total_storage_gb,
                    used_storage_gb = EXCLUDED.used_storage_gb,
                    available_storage_gb = EXCLUDED.available_storage_gb,
                    last_updated = EXCLUDED.last_updated
            """, (
                node[0],
                node[1],
                0,
                node[1],
                updated_at
            ))

            initialized_nodes.append({
                "node_id": node[0],
                "total_storage_gb": node[1],
                "used_storage_gb": 0,
                "available_storage_gb": node[1],
                "last_updated": updated_at
            })

        self.conn.commit()

        return {
            "success": True,
            "total_nodes_initialized": len(initialized_nodes),
            "nodes": initialized_nodes
        }


    def get_storage_usage(self):
        self.cursor.execute("""
            SELECT node_id, total_storage_gb, used_storage_gb, available_storage_gb, last_updated
            FROM node_storage_usage
        """)

        rows = self.cursor.fetchall()

        usage_list = []
        for row in rows:
            usage_list.append({
                "node_id": row[0],
                "total_storage_gb": row[1],
                "used_storage_gb": row[2],
                "available_storage_gb": row[3],
                "last_updated": row[4]
            })

        return {
            "success": True,
            "total_nodes": len(usage_list),
            "storage_usage": usage_list
        }

    def get_node_storage_usage(self, node_id: str):
        self.cursor.execute("""
            SELECT node_id, total_storage_gb, used_storage_gb, available_storage_gb, last_updated
            FROM node_storage_usage
            WHERE node_id = %s
        """, (node_id,))

        row = self.cursor.fetchone()

        if row is None:
            return {
                "success": False,
                "message": "Storage usage not found for this node"
            }

        return {
            "success": True,
            "node_id": row[0],
            "total_storage_gb": row[1],
            "used_storage_gb": row[2],
            "available_storage_gb": row[3],
            "last_updated": row[4]
        }

    def scan_node_health(self):
        now = datetime.now(timezone.utc)
        offline_threshold_minutes = 5
        cutoff_time = now - timedelta(minutes=offline_threshold_minutes)

        self.cursor.execute("""
            SELECT node_id, status, last_seen
            FROM nodes
            ORDER BY node_id
        """)

        nodes = self.cursor.fetchall()
        checked_nodes = []
        newly_marked_offline = []

        for node in nodes:
            node_id = node[0]
            status = node[1]
            last_seen = node[2]

            is_stale = False

            if last_seen is None:
                is_stale = True
            elif last_seen < cutoff_time:
                is_stale = True

            if is_stale and status != "offline":
                self.cursor.execute("""
                    UPDATE nodes
                    SET status = 'offline'
                    WHERE node_id = %s
                """, (node_id,))

                newly_marked_offline.append(node_id)

            checked_nodes.append({
                "node_id": node_id,
                "previous_status": status,
                "last_seen": str(last_seen),
                "is_stale": is_stale
            })

        self.conn.commit()

        return {
            "success": True,
            "threshold_minutes": offline_threshold_minutes,
            "nodes_checked": len(checked_nodes),
            "newly_marked_offline_count": len(newly_marked_offline),
            "newly_marked_offline": newly_marked_offline,
            "checked_nodes": checked_nodes
        }


    def get_allocations(self):
        self.cursor.execute("""
            SELECT allocation_id, node_id, file_size_gb, allocated_at, status
            FROM allocations
        """)

        rows = self.cursor.fetchall()
        allocation_list = []

        for row in rows:
            allocation_list.append({
                "allocation_id": row[0],
                "node_id": row[1],
                "file_size_gb": row[2],
                "allocated_at": row[3],
                "status": row[4]
            })

        return {
            "total_allocations": len(allocation_list),
            "allocations": allocation_list
        }
