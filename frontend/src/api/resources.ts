import { apiGet, apiPost, withQuery } from './client'
import type {
  AttentionQueue,
  Customer,
  DemandAnalytics,
  DemandAnalyticsParams,
  Enquiry,
  EnquiryListParams,
  FulfilmentCreate,
  HealthResponse,
  InventoryLot,
  Payment,
  PaymentCreate,
  Preorder,
  PreorderCreate,
  PreorderListParams,
  PreorderTransitionStatus,
  Product,
  Supplier,
  SupplierOrder,
  SupplierOrderGenerateDraft,
  SupplierOrderListParams,
  SupplierOrderReconcile,
  SupplierOrderTransitionStatus,
} from './types'

export function getHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>('/health')
}

export function getSuppliers(): Promise<Supplier[]> {
  return apiGet<Supplier[]>('/api/v1/suppliers')
}

export function getSupplier(supplierId: number): Promise<Supplier> {
  return apiGet<Supplier>(`/api/v1/suppliers/${supplierId}`)
}

export function getProducts(supplierId?: number): Promise<Product[]> {
  return apiGet<Product[]>(
    withQuery('/api/v1/products', { supplier_id: supplierId }),
  )
}

export function getProduct(productId: number): Promise<Product> {
  return apiGet<Product>(`/api/v1/products/${productId}`)
}

export function getCustomers(): Promise<Customer[]> {
  return apiGet<Customer[]>('/api/v1/customers')
}

export function getCustomer(customerId: number): Promise<Customer> {
  return apiGet<Customer>(`/api/v1/customers/${customerId}`)
}

export function getEnquiries(params: EnquiryListParams = {}): Promise<Enquiry[]> {
  return apiGet<Enquiry[]>(
    withQuery('/api/v1/enquiries', {
      customer_id: params.customer_id,
      product_id: params.product_id,
      outcome: params.outcome,
      open_only: params.open_only,
    }),
  )
}

export function getEnquiry(enquiryId: number): Promise<Enquiry> {
  return apiGet<Enquiry>(`/api/v1/enquiries/${enquiryId}`)
}

export function getPreorders(params: PreorderListParams = {}): Promise<Preorder[]> {
  return apiGet<Preorder[]>(
    withQuery('/api/v1/preorders', {
      customer_id: params.customer_id,
      product_id: params.product_id,
      status: params.status,
      enquiry_id: params.enquiry_id,
    }),
  )
}

export function getPreorder(preorderId: number): Promise<Preorder> {
  return apiGet<Preorder>(`/api/v1/preorders/${preorderId}`)
}

export function transitionPreorder(
  preorderId: number,
  status: PreorderTransitionStatus,
): Promise<Preorder> {
  return apiPost<Preorder>(`/api/v1/preorders/${preorderId}/transitions`, { status })
}

export function createPreorder(payload: PreorderCreate): Promise<Preorder> {
  return apiPost<Preorder>('/api/v1/preorders', payload)
}

export function fulfilPreorder(
  preorderId: number,
  payload: FulfilmentCreate,
): Promise<Preorder> {
  return apiPost<Preorder>(`/api/v1/preorders/${preorderId}/fulfil`, payload)
}

export function createPayment(
  preorderId: number,
  payload: PaymentCreate,
): Promise<Payment> {
  return apiPost<Payment>(`/api/v1/preorders/${preorderId}/payments`, payload)
}

export function getPayments(preorderId: number): Promise<Payment[]> {
  return apiGet<Payment[]>(`/api/v1/preorders/${preorderId}/payments`)
}

export function getPayment(preorderId: number, paymentId: number): Promise<Payment> {
  return apiGet<Payment>(`/api/v1/preorders/${preorderId}/payments/${paymentId}`)
}

export function getSupplierOrders(
  params: SupplierOrderListParams = {},
): Promise<SupplierOrder[]> {
  return apiGet<SupplierOrder[]>(
    withQuery('/api/v1/supplier-orders', {
      supplier_id: params.supplier_id,
      status: params.status,
    }),
  )
}

export function getSupplierOrder(supplierOrderId: number): Promise<SupplierOrder> {
  return apiGet<SupplierOrder>(`/api/v1/supplier-orders/${supplierOrderId}`)
}

export function generateSupplierOrderDraft(
  payload: SupplierOrderGenerateDraft,
): Promise<SupplierOrder> {
  return apiPost<SupplierOrder>('/api/v1/supplier-orders/generate-draft', payload)
}

export function placeSupplierOrder(supplierOrderId: number): Promise<SupplierOrder> {
  return apiPost<SupplierOrder>(`/api/v1/supplier-orders/${supplierOrderId}/place`, {})
}

export function transitionSupplierOrder(
  supplierOrderId: number,
  status: SupplierOrderTransitionStatus,
): Promise<SupplierOrder> {
  return apiPost<SupplierOrder>(`/api/v1/supplier-orders/${supplierOrderId}/transitions`, {
    status,
  })
}

export function reconcileSupplierOrder(
  supplierOrderId: number,
  payload: SupplierOrderReconcile,
): Promise<SupplierOrder> {
  return apiPost<SupplierOrder>(
    `/api/v1/supplier-orders/${supplierOrderId}/reconcile`,
    payload,
  )
}

export function getInventory(productId?: number): Promise<InventoryLot[]> {
  return apiGet<InventoryLot[]>(
    withQuery('/api/v1/inventory', { product_id: productId }),
  )
}

export function getInventoryLot(inventoryLotId: number): Promise<InventoryLot> {
  return apiGet<InventoryLot>(`/api/v1/inventory/${inventoryLotId}`)
}

export function getAttention(): Promise<AttentionQueue> {
  return apiGet<AttentionQueue>('/api/v1/attention')
}

export function getDemandAnalytics(
  params: DemandAnalyticsParams = {},
): Promise<DemandAnalytics> {
  return apiGet<DemandAnalytics>(
    withQuery('/api/v1/analytics/demand', {
      from: params.from,
      to: params.to,
    }),
  )
}
