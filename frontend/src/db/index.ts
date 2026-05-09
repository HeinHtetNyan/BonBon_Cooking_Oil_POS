import { openDB, type IDBPDatabase } from "idb";

interface BonBonDB {
  drafts: {
    key: string;
    value: {
      id: string;
      type: string;
      data: unknown;
      updatedAt: number;
    };
  };
  offlineQueue: {
    key: string;
    value: {
      id: string;
      method: string;
      url: string;
      body: unknown;
      createdAt: number;
    };
  };
}

let dbInstance: IDBPDatabase<BonBonDB> | null = null;

export async function getDB(): Promise<IDBPDatabase<BonBonDB>> {
  if (!dbInstance) {
    dbInstance = await openDB<BonBonDB>("bonbon-erp", 1, {
      upgrade(db) {
        if (!db.objectStoreNames.contains("drafts")) {
          db.createObjectStore("drafts", { keyPath: "id" });
        }
        if (!db.objectStoreNames.contains("offlineQueue")) {
          db.createObjectStore("offlineQueue", { keyPath: "id" });
        }
      },
    });
  }
  return dbInstance;
}

export async function saveDraft(type: string, id: string, data: unknown) {
  const db = await getDB();
  await db.put("drafts", { id: `${type}:${id}`, type, data, updatedAt: Date.now() });
}

export async function getDraft(type: string, id: string) {
  const db = await getDB();
  return db.get("drafts", `${type}:${id}`);
}

export async function deleteDraft(type: string, id: string) {
  const db = await getDB();
  await db.delete("drafts", `${type}:${id}`);
}
