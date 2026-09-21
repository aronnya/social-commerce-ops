/** JSON representations of Numeric(12, 2). FastAPI may emit a number or a decimal string. */
export type Money = string | number

export type EnquiryOutcome =
  | 'PREORDERED'
  | 'TOO_EXPENSIVE'
  | 'SUPPLIER_UNAVAILABLE'
  | 'CUSTOMER_GHOSTED'
  | 'WRONG_SIZE'
  | 'NOT_INTERESTED'

export type PreorderStatus =
  | 'CONFIRMED'
  | 'ORDERED_FROM_SUPPLIER'
  | 'ARRIVED'
  | 'READY_FOR_CUSTOMER'
  | 'FULFILLED'
  | 'CANCELLED'
  | 'SUPPLIER_UNAVAILABLE'

export type PreorderTransitionStatus = Exclude<PreorderStatus, 'FULFILLED'>

export type PaymentMethod = 'BANK_TRANSFER' | 'REVOLUT'

export type FulfilmentCreate = {
  method: FulfilmentMethod
  postage_type?: PostageType | null
  delivery_address?: string | null
  postage_cost?: Money | null
  tracking_reference?: string | null
  notes?: string | null
}

export type PaymentCreate = {
  amount: Money
  method: PaymentMethod
  reference?: string | null
  paid_at?: string | null
  notes?: string | null
}

export type PreorderCreate = {
  customer_id: number
  product_id: number
  enquiry_id?: number | null
  quantity?: number
  agreed_price?: Money | null
  notes?: string | null
}

export type PaymentSummaryStatus = 'UNPAID' | 'PARTIALLY_PAID' | 'PAID' | 'OVERPAID'

export type FulfilmentMethod = 'HOME_COLLECTION' | 'POST'

export type PostageType = 'REGULAR' | 'REGISTERED'

export type SupplierOrderStatus =
  | 'DRAFT'
  | 'PLACED'
  | 'CONFIRMED'
  | 'DISPATCHED'
  | 'ARRIVED'
  | 'RECONCILED'

export type SupplierOrderTransitionStatus = 'CONFIRMED' | 'DISPATCHED' | 'ARRIVED'

export type SupplierOrderGenerateDraft = {
  supplier_id: number
  preorder_ids?: number[]
}

export type ReconciliationLineInput = {
  line_id: number
  received_quantity: number
  arrived_preorder_ids?: number[]
}

export type SupplierOrderReconcile = {
  lines: ReconciliationLineInput[]
  reconciliation_notes?: string | null
}

export type AttentionType =
  | 'preorder_overpaid'
  | 'supplier_order_needs_reconciliation'
  | 'preorder_needs_customer_ready'
  | 'preorder_needs_fulfilment'
  | 'supplier_order_draft_needs_placement'
  | 'preorder_needs_supplier_order'

export type AttentionEntityType = 'preorder' | 'supplier_order'

export type LostDemandReason =
  | 'TOO_EXPENSIVE'
  | 'SUPPLIER_UNAVAILABLE'
  | 'CUSTOMER_GHOSTED'
  | 'WRONG_SIZE'
  | 'NOT_INTERESTED'

export type HealthResponse = {
  status: string
}

export type Supplier = {
  id: number
  name: string
  contact_name: string | null
  phone: string | null
  whatsapp: string | null
  email: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export type SupplierCreate = {
  name: string
  contact_name?: string | null
  phone?: string | null
  whatsapp?: string | null
  email?: string | null
  notes?: string | null
}

export type Product = {
  id: number
  supplier_id: number
  name: string
  description: string | null
  style: string | null
  colour: string | null
  size: string | null
  supplier_cost: Money | null
  selling_price: Money | null
  notes: string | null
  created_at: string
  updated_at: string
}

export type ProductCreate = {
  supplier_id: number
  name: string
  description?: string | null
  style?: string | null
  colour?: string | null
  size?: string | null
  supplier_cost?: Money | null
  selling_price?: Money | null
  notes?: string | null
}

export type ProductUpdate = {
  supplier_id?: number
  name?: string
  description?: string | null
  style?: string | null
  colour?: string | null
  size?: string | null
  supplier_cost?: Money | null
  selling_price?: Money | null
  notes?: string | null
}

export type Customer = {
  id: number
  name: string
  phone: string | null
  facebook_name: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export type CustomerCreate = {
  name: string
  phone?: string | null
  facebook_name?: string | null
  notes?: string | null
}

export type CustomerUpdate = {
  name?: string
  phone?: string | null
  facebook_name?: string | null
  notes?: string | null
}

export type Enquiry = {
  id: number
  customer_id: number
  product_id: number
  quantity: number
  outcome: EnquiryOutcome | null
  notes: string | null
  enquired_at: string
  created_at: string
  updated_at: string
}

export type EnquiryCreate = {
  customer_id: number
  product_id: number
  quantity?: number
  notes?: string | null
}

export type EnquiryUpdate = {
  quantity?: number
  outcome?: EnquiryOutcome | null
  notes?: string | null
  enquired_at?: string | null
}

export type PaymentSummary = {
  total_amount: Money | null
  amount_paid: Money
  outstanding_balance: Money | null
  status: PaymentSummaryStatus | null
}

export type Fulfilment = {
  id: number
  preorder_id: number
  method: FulfilmentMethod
  postage_type: PostageType | null
  delivery_address: string | null
  postage_cost: Money | null
  tracking_reference: string | null
  notes: string | null
  fulfilled_at: string
  created_at: string
  updated_at: string
}

export type Preorder = {
  id: number
  customer_id: number
  product_id: number
  enquiry_id: number | null
  quantity: number
  status: PreorderStatus
  agreed_price: Money | null
  notes: string | null
  created_at: string
  updated_at: string
  payment_summary: PaymentSummary
  fulfilment: Fulfilment | null
}

export type Payment = {
  id: number
  preorder_id: number
  amount: Money
  method: PaymentMethod
  reference: string | null
  paid_at: string
  notes: string | null
  created_at: string
  updated_at: string
}

export type SupplierOrderAllocation = {
  id: number
  preorder_id: number
  quantity: number
}

export type SupplierOrderLine = {
  id: number
  product_id: number
  quantity: number
  received_quantity: number | null
  unit_cost: Money | null
  notes: string | null
  allocations: SupplierOrderAllocation[]
}

export type SupplierOrder = {
  id: number
  supplier_id: number
  status: SupplierOrderStatus
  notes: string | null
  placed_at: string | null
  reconciled_at: string | null
  reconciliation_notes: string | null
  created_at: string
  updated_at: string
  lines: SupplierOrderLine[]
}

export type InventoryLot = {
  id: number
  product_id: number
  quantity_on_hand: number
  supplier_order_line_id: number | null
  created_at: string
  updated_at: string
}

export type AttentionItem = {
  type: AttentionType
  entity_type: AttentionEntityType
  entity_id: number
  occurred_at: string
  customer_id: number | null
  product_id: number | null
  supplier_id: number | null
  outstanding_balance: Money | null
}

export type AttentionCounts = {
  preorder_overpaid: number
  supplier_order_needs_reconciliation: number
  preorder_needs_customer_ready: number
  preorder_needs_fulfilment: number
  supplier_order_draft_needs_placement: number
  preorder_needs_supplier_order: number
}

export type AttentionQueue = {
  items: AttentionItem[]
  counts: AttentionCounts
}

export type DemandOverview = {
  total_enquiries: number
  open_enquiries: number
  resolved_enquiries: number
  converted_enquiries: number
  lost_enquiries: number
  requested_quantity: number
  conversion_rate: Money | null
  unlinked_preordered_outcomes: number
  linked_preorder_outcome_mismatch: number
}

export type LostDemandBucket = {
  reason: LostDemandReason
  count: number
}

export type ProductDemandRow = {
  product_id: number
  name: string
  style: string | null
  colour: string | null
  size: string | null
  supplier_id: number
  supplier_name: string
  enquiry_count: number
  distinct_customers: number
  requested_quantity: number
  converted_enquiries: number
  lost_enquiries: number
  open_enquiries: number
  conversion_rate: Money | null
}

export type SupplierDemandRow = {
  supplier_id: number
  name: string
  enquiry_count: number
  distinct_customers: number
  requested_quantity: number
  converted_enquiries: number
  lost_enquiries: number
  open_enquiries: number
  conversion_rate: Money | null
}

/** All-time supplier reconciliation snapshot. Not customer fulfilment. */
export type SupplierReconciliationSnapshot = {
  date_basis: 'all_time'
  reconciled_order_count: number
  ordered_quantity: number
  received_quantity: number
  shortage_units: number
  excess_units: number
}

export type DemandAnalytics = {
  from: string | null
  to: string | null
  overview: DemandOverview
  lost_demand: LostDemandBucket[]
  products: ProductDemandRow[]
  suppliers: SupplierDemandRow[]
  fulfilment: SupplierReconciliationSnapshot
}

export type EnquiryListParams = {
  customer_id?: number
  product_id?: number
  outcome?: EnquiryOutcome
  open_only?: boolean
}

export type PreorderListParams = {
  customer_id?: number
  product_id?: number
  status?: PreorderStatus
  enquiry_id?: number
}

export type SupplierOrderListParams = {
  supplier_id?: number
  status?: SupplierOrderStatus
}

export type DemandAnalyticsParams = {
  from?: string
  to?: string
}
