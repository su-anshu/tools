# Split Logic Documentation for Packing Plan

## Overview
This document explains the split logic used in the packing plan system. When a product has a "Split Into" field in the master data, it needs to be expanded into multiple physical items based on weight variants.

## Key Concepts

### 1. Split Products
- A product can be split into multiple variants based on weight
- Example: "Coconut Thekua" (0.7kg) can be split into:
  - "Coconut Thekua 0.35" (split variant 1)
  - "Coconut Thekua 0.35" (split variant 2)
- The original product name is preserved with its weight appended for display
- Each split variant has its own FNSKU, weight, and other properties

### 2. Data Structure

#### Master Data Fields:
- `Name`: Product name (e.g., "Coconut Thekua")
- `ASIN`: Amazon ASIN code
- `Net Weight`: Original product weight (e.g., "0.7kg" or "0.7")
- `Split Into`: Comma-separated list of split sizes (e.g., "0.35, 0.35")
- `FNSKU`: Fulfillment Network SKU
- `Packet Size`, `Packet used`, `MRP`, `FSSAI`: Other product properties

#### Output Structure for Split Products:
```javascript
{
  item: "Coconut Thekua 0.7",              // Original name + weight (for display)
  item_name_for_labels: "Coconut Thekua",  // Original name without weight (for labels)
  weight: "0.35",                          // Split variant weight
  Qty: 1,                                  // Quantity ordered
  Packet Size: "...",
  Packet used: "...",
  ASIN: "...",
  MRP: "...",
  FNSKU: "...",
  FSSAI: "...",
  is_split: true                           // Flag indicating this is a split product
}
```

## Algorithm

### Step 1: Check for Split Information
```javascript
// Check if product has split information
const split = baseProduct["Split Into"]?.trim();
const hasSplit = split && split !== "" && !isEmptyValue(split);
```

### Step 2: Extract Base Product Information
```javascript
const name = baseProduct["Name"] || "Unknown Product";
const asin = orderRow["ASIN"];
const qty = parseInt(orderRow["Qty"]) || 1;

// Extract base weight (handles int, float, string, NaN)
let baseWeight = "";
const baseWeightRaw = baseProduct["Net Weight"] || baseProduct["NetWeight"];

if (baseWeightRaw != null && !isNaN(baseWeightRaw)) {
  if (typeof baseWeightRaw === "number") {
    baseWeight = String(baseWeightRaw).trim();
  } else {
    baseWeight = String(baseWeightRaw).trim();
  }
}
```

### Step 3: Construct Original Name with Weight
```javascript
// For split products, append weight to original name
let originalNameWithWeight = name;

if (baseWeight) {
  // Remove "kg" suffix if present for cleaner display
  const weightDisplay = baseWeight.toLowerCase().endsWith("kg") 
    ? baseWeight.replace(/kg/gi, "").trim() 
    : baseWeight;
  
  originalNameWithWeight = `${name} ${weightDisplay}`;
  // Example: "Coconut Thekua" + "0.7" = "Coconut Thekua 0.7"
}
```

### Step 4: Process Split Variants
```javascript
if (hasSplit) {
  // Parse split sizes (comma-separated, remove "kg" suffix)
  const sizes = split.split(",").map(s => 
    s.trim().replace(/kg/gi, "").trim()
  );
  
  let splitFound = false;
  
  // For each split size, find matching variant in master data
  for (const size of sizes) {
    // Find variant in master data where:
    // - Name matches original product name
    // - Net Weight (normalized) matches split size
    const variant = masterData.find(product => {
      const productName = product["Name"];
      const productWeight = String(product["Net Weight"] || product["NetWeight"] || "")
        .replace(/kg/gi, "").trim();
      
      return productName === name && productWeight === size;
    });
    
    if (variant) {
      const variantFNSKU = String(variant["FNSKU"] || "").trim();
      const status = (variantFNSKU && !isEmptyValue(variantFNSKU)) 
        ? "✅ READY" 
        : "⚠️ MISSING FNSKU";
      
      // Create physical row for this split variant
      physicalRows.push({
        item: originalNameWithWeight,        // "Coconut Thekua 0.7"
        item_name_for_labels: name,          // "Coconut Thekua"
        weight: variant["Net Weight"] || "N/A",
        Qty: qty,
        "Packet Size": variant["Packet Size"] || "N/A",
        "Packet used": variant["Packet used"] || "N/A",
        ASIN: variant["ASIN"] || asin,
        MRP: variant["M.R.P"] || "N/A",
        FNSKU: variantFNSKU || "MISSING",
        FSSAI: variant["FSSAI"] || "N/A",
        "Packed Today": "",
        "Available": "",
        Status: status,
        is_split: true
      });
      
      splitFound = true;
    }
  }
  
  // If no split variants found, add to missing products
  if (!splitFound) {
    missingProducts.push({
      ASIN: asin,
      Issue: "Split sizes not found in master file",
      Product: name,
      "Split Info": split,
      Qty: qty
    });
  }
}
```

### Step 5: Handle Non-Split Products
```javascript
else {
  // No split information - use base product as-is
  const fnsku = String(baseProduct["FNSKU"] || "").trim();
  const status = (fnsku && !isEmptyValue(fnsku)) 
    ? "✅ READY" 
    : "⚠️ MISSING FNSKU";
  
  physicalRows.push({
    item: name,
    item_name_for_labels: name,
    weight: baseProduct["Net Weight"] || "N/A",
    Qty: qty,
    "Packet Size": baseProduct["Packet Size"] || "N/A",
    "Packet used": baseProduct["Packet used"] || "N/A",
    ASIN: asin,
    MRP: baseProduct["M.R.P"] || "N/A",
    FNSKU: fnsku || "MISSING",
    FSSAI: baseProduct["FSSAI"] || "N/A",
    "Packed Today": "",
    "Available": "",
    Status: status,
    is_split: false
  });
}
```

### Step 6: Group and Aggregate
```javascript
// After processing all orders, group identical items and sum quantities
// Group by all columns except Qty, then sum Qty
const grouped = physicalRows.reduce((acc, row) => {
  const key = JSON.stringify({
    item: row.item,
    item_name_for_labels: row.item_name_for_labels,
    weight: row.weight,
    "Packet Size": row["Packet Size"],
    "Packet used": row["Packet used"],
    ASIN: row.ASIN,
    MRP: row.MRP,
    FNSKU: row.FNSKU,
    FSSAI: row.FSSAI,
    "Packed Today": row["Packed Today"],
    "Available": row["Available"],
    Status: row.Status,
    is_split: row.is_split
  });
  
  if (acc[key]) {
    acc[key].Qty += row.Qty;
  } else {
    acc[key] = { ...row };
  }
  
  return acc;
}, {});

const finalPhysicalPlan = Object.values(grouped);
```

## Helper Functions

### isEmptyValue
```javascript
function isEmptyValue(value) {
  if (value === null || value === undefined) return true;
  const str = String(value).trim().toLowerCase();
  return str === "" || str === "nan" || str === "none" || str === "n/a";
}
```

## Complete JavaScript/TypeScript Example

```typescript
interface OrderRow {
  ASIN: string;
  Qty: number;
}

interface MasterProduct {
  Name: string;
  ASIN: string;
  "Net Weight": string | number;
  "Split Into"?: string;
  FNSKU?: string;
  "Packet Size"?: string;
  "Packet used"?: string;
  "M.R.P"?: string;
  FSSAI?: string;
}

interface PhysicalRow {
  item: string;
  item_name_for_labels: string;
  weight: string;
  Qty: number;
  "Packet Size": string;
  "Packet used": string;
  ASIN: string;
  MRP: string;
  FNSKU: string;
  FSSAI: string;
  "Packed Today": string;
  "Available": string;
  Status: string;
  is_split: boolean;
}

function expandToPhysical(
  orders: OrderRow[],
  masterData: MasterProduct[]
): { physicalRows: PhysicalRow[]; missingProducts: any[] } {
  const physicalRows: PhysicalRow[] = [];
  const missingProducts: any[] = [];
  
  // Create ASIN lookup for O(1) access
  const asinLookup = new Map<string, MasterProduct>();
  masterData.forEach(product => {
    const asin = String(product.ASIN || "").trim();
    if (asin && !asinLookup.has(asin)) {
      asinLookup.set(asin, product);
    }
  });
  
  for (const orderRow of orders) {
    try {
      const asin = orderRow.ASIN || "UNKNOWN";
      const qty = parseInt(String(orderRow.Qty)) || 1;
      
      // Find base product in master data
      const baseProduct = asinLookup.get(asin);
      
      if (!baseProduct) {
        missingProducts.push({
          ASIN: asin,
          Issue: "Not found in master file",
          Qty: qty
        });
        
        physicalRows.push({
          item: `UNKNOWN PRODUCT (${asin})`,
          item_name_for_labels: `UNKNOWN PRODUCT (${asin})`,
          weight: "N/A",
          Qty: qty,
          "Packet Size": "N/A",
          "Packet used": "N/A",
          ASIN: asin,
          MRP: "N/A",
          FNSKU: "MISSING",
          FSSAI: "N/A",
          "Packed Today": "",
          "Available": "",
          Status: "⚠️ MISSING FROM MASTER",
          is_split: false
        });
        continue;
      }
      
      const name = baseProduct.Name || "Unknown Product";
      const split = String(baseProduct["Split Into"] || "").trim();
      const hasSplit = split && split !== "" && !isEmptyValue(split);
      
      // Extract base weight
      let baseWeight = "";
      const baseWeightRaw = baseProduct["Net Weight"];
      if (baseWeightRaw != null && !isNaN(Number(baseWeightRaw))) {
        baseWeight = String(baseWeightRaw).trim();
      }
      
      // Construct original name with weight
      let originalNameWithWeight = name;
      if (baseWeight && !isEmptyValue(baseWeight)) {
        const weightDisplay = baseWeight.toLowerCase().endsWith("kg")
          ? baseWeight.replace(/kg/gi, "").trim()
          : baseWeight;
        originalNameWithWeight = `${name} ${weightDisplay}`;
      }
      
      const fnsku = String(baseProduct.FNSKU || "").trim();
      
      // Check if FNSKU is missing
      if (isEmptyValue(fnsku)) {
        missingProducts.push({
          ASIN: asin,
          Issue: "Missing FNSKU",
          Product: name,
          Qty: qty
        });
      }
      
      // Handle split products
      if (hasSplit) {
        const sizes = split.split(",").map(s => 
          s.trim().replace(/kg/gi, "").trim()
        );
        
        let splitFound = false;
        
        for (const size of sizes) {
          // Find variant in master data
          const variant = masterData.find(product => {
            const productName = product.Name;
            const productWeight = String(product["Net Weight"] || "")
              .replace(/kg/gi, "").trim();
            return productName === name && productWeight === size;
          });
          
          if (variant) {
            const variantFNSKU = String(variant.FNSKU || "").trim();
            const status = (variantFNSKU && !isEmptyValue(variantFNSKU))
              ? "✅ READY"
              : "⚠️ MISSING FNSKU";
            
            physicalRows.push({
              item: originalNameWithWeight,
              item_name_for_labels: name,
              weight: String(variant["Net Weight"] || "N/A"),
              Qty: qty,
              "Packet Size": String(variant["Packet Size"] || "N/A"),
              "Packet used": String(variant["Packet used"] || "N/A"),
              ASIN: variant.ASIN || asin,
              MRP: String(variant["M.R.P"] || "N/A"),
              FNSKU: variantFNSKU || "MISSING",
              FSSAI: String(variant.FSSAI || "N/A"),
              "Packed Today": "",
              "Available": "",
              Status: status,
              is_split: true
            });
            
            splitFound = true;
          }
        }
        
        if (!splitFound) {
          missingProducts.push({
            ASIN: asin,
            Issue: "Split sizes not found in master file",
            Product: name,
            "Split Info": split,
            Qty: qty
          });
        }
      } else {
        // No split - use base product
        const status = (fnsku && !isEmptyValue(fnsku))
          ? "✅ READY"
          : "⚠️ MISSING FNSKU";
        
        physicalRows.push({
          item: name,
          item_name_for_labels: name,
          weight: String(baseProduct["Net Weight"] || "N/A"),
          Qty: qty,
          "Packet Size": String(baseProduct["Packet Size"] || "N/A"),
          "Packet used": String(baseProduct["Packet used"] || "N/A"),
          ASIN: asin,
          MRP: String(baseProduct["M.R.P"] || "N/A"),
          FNSKU: fnsku || "MISSING",
          FSSAI: String(baseProduct.FSSAI || "N/A"),
          "Packed Today": "",
          "Available": "",
          Status: status,
          is_split: false
        });
      }
    } catch (error) {
      console.error(`Error processing order ${orderRow.ASIN}:`, error);
      continue;
    }
  }
  
  // Group identical items and sum quantities
  const grouped = physicalRows.reduce((acc, row) => {
    const key = JSON.stringify({
      item: row.item,
      item_name_for_labels: row.item_name_for_labels,
      weight: row.weight,
      "Packet Size": row["Packet Size"],
      "Packet used": row["Packet used"],
      ASIN: row.ASIN,
      MRP: row.MRP,
      FNSKU: row.FNSKU,
      FSSAI: row.FSSAI,
      "Packed Today": row["Packed Today"],
      "Available": row["Available"],
      Status: row.Status,
      is_split: row.is_split
    });
    
    if (acc[key]) {
      acc[key].Qty += row.Qty;
    } else {
      acc[key] = { ...row };
    }
    
    return acc;
  }, {} as Record<string, PhysicalRow>);
  
  return {
    physicalRows: Object.values(grouped),
    missingProducts
  };
}

function isEmptyValue(value: any): boolean {
  if (value === null || value === undefined) return true;
  const str = String(value).trim().toLowerCase();
  return str === "" || str === "nan" || str === "none" || str === "n/a";
}
```

## Edge Cases and Error Handling

1. **Missing Master Data**: If product not found in master, create "UNKNOWN PRODUCT" entry
2. **Missing Split Variants**: If split sizes specified but variants not found, add to missing products
3. **Empty Split Field**: If "Split Into" is empty/null, treat as regular product
4. **Weight Normalization**: Handle weights with/without "kg" suffix, integers, floats, strings
5. **Missing FNSKU**: Mark as "MISSING" but still create physical row
6. **Quantity Aggregation**: Group identical items and sum quantities after expansion

## React Integration Tips

1. **State Management**: Store `physicalRows` and `missingProducts` in React state
2. **Memoization**: Use `useMemo` for expensive operations like grouping
3. **Loading States**: Show loading indicator during processing
4. **Error Boundaries**: Wrap in error boundary to catch processing errors
5. **Performance**: For large datasets, consider Web Workers for processing

## Example Usage in React

```typescript
import { useState, useMemo } from 'react';

function PackingPlanComponent() {
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [masterData, setMasterData] = useState<MasterProduct[]>([]);
  
  const { physicalRows, missingProducts } = useMemo(() => {
    if (orders.length === 0 || masterData.length === 0) {
      return { physicalRows: [], missingProducts: [] };
    }
    return expandToPhysical(orders, masterData);
  }, [orders, masterData]);
  
  return (
    <div>
      {/* Render physicalRows and missingProducts */}
    </div>
  );
}
```

