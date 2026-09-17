export interface HistoryTurn {
  role: "user" | "assistant";
  text: string;
}

export interface OrderCheck {
  name: string;
  status: string;
  details?: Record<string, unknown>;
}

export interface OrderLine {
  line_no: number;
  sku: string;
  product: string;
  colour: string | null;
  product_family: string | null;
  product_type: string | null;
  quantity: number;
  unit: string;
  converted_quantity: number;
  converted_unit: string;
  conversion_note: string | null;
  squares?: number;
  unit_price: number;
  price_unit: string;
  line_subtotal: number;
  source: "customer" | "add_on";
  included: boolean;
  add_on_rule?: string | null;
  rationale?: string | null;
  qualifying?: boolean;
  swatch_hex?: string | null;
  badges?: string[];
  image_url?: string | null;
  colour_collection?: string | null;
  price_tier?: string | null;
  inventory?: {
    warehouse?: string;
    warehouse_id?: string;
    available?: number;
    unit?: string;
    restock_date?: string | null;
    backorder_risk?: string | null;
    needed?: number;
    alternate?: { warehouse: string; available: number };
  };
  inventory_note?: string;
  warnings?: string[];
}

export interface DiscountLine {
  discount_id: string;
  name: string;
  kind: "volume" | "seasonal" | "bundle" | "account";
  percent: number;
  amount: number;
  badge?: string | null;
  applies_to_lines: number[];
  note?: string;
  description?: string | null;
}

export interface Pricing {
  currency: string;
  subtotal: number;
  discounts: DiscountLine[];
  discount_total: number;
  total: number;
  commission?: { rep_id: string | null; rep_name: string | null; rate: number; amount: number } | null;
  next_volume_tier?: { discount_id: string; name: string; percent: number; squares_short: number } | null;
  included_line_count: number;
}

// Structured, form-ready fields -- populated whenever the customer/product
// were resolved (ready_for_review or blocked); absent for needs_clarification.
export interface OrderDetails {
  customer_id: string | null;
  customer_name: string | null;
  trade_name?: string | null;
  customer_type?: string | null;
  sales_rep_id?: string | null;
  sales_rep_name?: string | null;
  lines: OrderLine[];
  sku: string | null;
  product: string | null;
  colour: string | null;
  quantity: number | null;
  unit: string | null;
  converted_quantity: number | null;
  converted_unit: string | null;
  conversion_note: string | null;
  total_squares?: number;
  delivery_city: string | null;
  delivery_date: string | null;
  delivery_date_resolved: string | null;
  delivery_method?: string | null;
  delivery_note: string | null;
  include_add_ons?: boolean;
  recommended_add_ons: string[];
  add_on_note: string | null;
  pricing?: Pricing;
  warnings: string[];
  customer_match_status: string | null;
  product_match_status: string | null;
  credit_check_status: string | null;
  inventory_check_status: string | null;
  duplicate_check_status: string | null;
  checks: OrderCheck[];
}

export interface RoofEstimate {
  status: "ok" | "needs_input";
  method?: string;
  footprint_sqft?: number;
  pitch?: string;
  pitch_factor?: number;
  roof_sqft?: number;
  waste_percent?: number;
  order_sqft?: number;
  squares?: number;
  assumptions?: string[];
  questions?: string[];
  inputs?: Record<string, unknown>;
}

export interface Clarification {
  type: string;
  quick_replies?: string[];
  proposed_quantity?: number;
  unit?: string;
  missing?: string[];
  questions?: string[];
}

export interface ProductCard {
  sku: string;
  product_name: string;
  product_family: string | null;
  colour: string | null;
  colour_collection?: string | null;
  product_type?: string | null;
  unit_price: number | null;
  price_unit: string | null;
  price_per_square: number | null;
  coverage?: number | null;
  swatch_hex: string | null;
  image_url: string | null;
  badges: string[];
  price_tier?: string | null;
}

export interface Contractor {
  contractorId: string;
  name: string;
  city: string;
  state: string;
  zip: string;
  distanceMiles: number;
  phone: string;
  rating: number;
  reviewCount: number;
  certificationTier: "presidents_club" | "master_elite" | "certified_plus" | "certified";
  certificationLabel: string;
  warrantiesOffered: string[];
  awards: string[];
  specialties: string[];
  yearsCertified: number | null;
  residential: boolean;
  commercial: boolean;
  acceptsQuoteRequests: boolean;
}

export interface ResolvedLocation {
  zip: string;
  city: string;
  state: string;
  county: string;
  regionId: string;
}

export interface GuardrailItem {
  key: string;
  label: string;
  status: string;
}

export interface OrderChatResponse {
  status: "ready_for_review" | "blocked" | "needs_clarification";
  order_session_id?: string | null;
  agent_message?: string | null;
  agent_timeline: string[];
  order_details?: OrderDetails | null;
  estimate?: RoofEstimate | null;
  clarification?: Clarification | null;
  products?: ProductCard[];
  guardrails?: GuardrailItem[];
}

export interface OrderConfirmResponse {
  status: string;
  message: string;
  erp_submission?: string;
  confirmation?: ConfirmedOrderRecord | null;
}

export interface Source {
  document_id: string;
  title: string;
  version: string;
}

export interface Escalation {
  destination: string;
  reason: string;
  urgent?: boolean;
}

export interface ReviewInfo {
  required: boolean;
  kind: "auto" | "human_review" | "escalation";
  review_id?: string;
  reasons?: string[];
  threshold?: number;
  urgent?: boolean;
}

export type WarrantyStatus = "answered" | "needs_review" | "no_source" | "escalated" | "urgent_escalation";

export interface WarrantyChatResponse {
  status: WarrantyStatus;
  answer: string | null;
  sources: Source[];
  escalation?: Escalation | null;
  agent_timeline: string[];
  guardrails?: GuardrailItem[];
  confidence?: number | null;
  review?: ReviewInfo | null;
  products?: ProductCard[];
}

export type RoutedTo = "order" | "warranty" | "contractor" | "general" | "chat";

export interface AssistantChatResponse {
  routed_to: RoutedTo;
  status: string;
  agent_message?: string | null;
  order_session_id?: string | null;
  order_details?: OrderDetails | null;
  estimate?: RoofEstimate | null;
  clarification?: Clarification | null;
  guardrails?: GuardrailItem[];
  answer?: string | null;
  sources: Source[];
  escalation?: Escalation | null;
  confidence?: number | null;
  review?: ReviewInfo | null;
  contractors?: Contractor[];
  location?: ResolvedLocation | null;
  products?: ProductCard[];
  order?: Record<string, unknown> | null;
  agent_timeline: string[];
  tone: "neutral" | "frustrated";
  handoff_suggested: boolean;
}

export interface FeedbackPayload {
  rating: "up" | "down";
  route?: string | null;
  status?: string | null;
  user_message?: string | null;
  assistant_message?: string | null;
  comment?: string | null;
}

export interface EmailDraftResponse {
  recap: string;
  agent_timeline: string[];
}

export interface InboxEmail {
  emailId: string;
  fromName: string;
  fromEmail: string;
  accountId: string;
  customerName: string;
  tradeName?: string | null;
  subject: string;
  receivedAt: string;
  category?: "order" | "warranty" | "contractor" | "mixed" | string;
  body: string;
  read: boolean;
}

export interface EmailIntakeItem {
  email_id: string;
  status: "processed" | "not_found";
  intent?: string | null;
  summary?: string | null;
  request?: string | null;
  email?: Partial<InboxEmail> | null;
  result?: AssistantChatResponse | null;
}

export interface SalesRep {
  repId: string;
  name: string;
  initials: string;
  title: string;
  email: string;
  phone: string;
  territory: string;
  states: string[];
  cities: string[];
  commissionRate: number;
  quotaUsd: number;
  accounts: string[];
}

export interface RepCustomer {
  accountId: string;
  customerName: string;
  tradeName?: string | null;
  customerType?: string | null;
  city: string;
  state: string;
  zip?: string;
  creditStatus: string;
  creditHold: boolean;
  creditLimit: number;
  availableCredit: number;
  creditLimitUsedPercent: number;
}

export interface RepOrder {
  orderId: string;
  accountId: string;
  customerPo?: string | null;
  sku: string | null;
  quantity: number | null;
  unit: string | null;
  squares?: number | null;
  orderDate: string;
  deliveryDate?: string | null;
  deliveryCity?: string | null;
  channel?: string | null;
  status?: string | null;
  totalUsd?: number | null;
  lines?: Array<{ sku: string; productName?: string; quantity: number; unit: string; extendedPriceUsd?: number; colour?: string | null }>;
}

export interface RepDashboard {
  rep: SalesRep;
  accounts: RepCustomer[];
  orders: RepOrder[];
  confirmed_this_session: ConfirmedOrderRecord[];
  inbox_unread: number;
  commission: {
    rate: number;
    booked_sales_usd: number;
    booked_commission_usd: number;
    session_sales_usd: number;
    session_commission_usd: number;
    pipeline_usd: number;
    quota_usd: number | null;
    quota_progress: number | null;
  };
}

export interface UseCase {
  id: string;
  group: string;
  title: string;
  prompt: string;
  expects: string;
}

export interface ReviewItem {
  review_id: string;
  created_at: string;
  status: "pending" | "resolved";
  route: string;
  question: string;
  draft_answer: string | null;
  confidence: number;
  reasons: string[];
  sources: Source[];
  location: string | null;
  decision?: string;
  final_answer?: string | null;
  reviewer?: string | null;
  resolved_at?: string;
}

export interface PhotoAnalysis {
  isRoofingRelated: boolean;
  whatIsVisible: string;
  possibleIssues?: string[];
  urgentSigns?: boolean;
  productGuess?: string | null;
  questionForAdvisor?: string;
}

export interface PhotoResponse {
  status: "analyzed" | "not_a_roof";
  analysis: PhotoAnalysis;
  question?: string | null;
  warranty?: WarrantyChatResponse | null;
  agent_timeline: string[];
}

export interface MetricsSummary {
  total_requests: number;
  average_latency_ms: number | null;
  fastest_response_ms: number | null;
  slowest_response_ms: number | null;
  successful_requests: number;
  failed_requests: number;
  smart_order_requests: number;
  warranty_requests: number;
  average_tokens: number | null;
  total_tokens: number | null;
  active_model: string | null;
  total_orders: number;
  confirmed_orders: number;
  blocked_orders: number;
  ready_for_review_orders: number;
  warning_orders: number;
  recent_latency: Array<{ timestamp: string; latency_ms: number | null; type: string }>;
}

export interface MetricsRequestRecord {
  request_id: string;
  timestamp: string;
  request_type: string;
  user_request: string;
  model_name: string | null;
  status: string;
  total_latency_ms: number | null;
  model_latency_ms: number | null;
  retrieval_latency_ms: number | null;
  tool_latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  guardrails: GuardrailItem[];
}

export interface ConfirmedOrderRecord {
  confirmation_id: string;
  order_session_id: string;
  confirmed_at: string;
  customer_id: string | null;
  customer_name: string | null;
  trade_name?: string | null;
  sales_rep_id?: string | null;
  product: string | null;
  sku: string | null;
  color: string | null;
  quantity: number | null;
  unit: string | null;
  total_squares?: number | null;
  lines?: Array<{ sku: string; product: string; colour: string | null; quantity: number; unit: string; unit_price: number; line_subtotal: number; source: string }>;
  order_subtotal?: number | null;
  discount_total?: number | null;
  discounts?: string[];
  order_total?: number | null;
  commission_rate?: number | null;
  commission_amount?: number | null;
  delivery_city: string | null;
  delivery_date: string | null;
  delivery_method?: string | null;
  credit_status: string | null;
  inventory_status: string | null;
  duplicate_warning: boolean;
  duplicate_order_id: string | null;
  final_status: "CONFIRMED";
}

export interface OrderHistoryRecord {
  order_session_id: string | null;
  timestamp: string;
  confirmation_time?: string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  sku?: string | null;
  product?: string | null;
  quantity?: number | null;
  unit?: string | null;
  delivery_city?: string | null;
  line_count?: number;
  total_squares?: number | null;
  order_total?: number | null;
  sales_rep_id?: string | null;
  final_status: string;
  credit_check_status?: string | null;
  inventory_check_status?: string | null;
  duplicate_check_status?: string | null;
  customer_match_status?: string | null;
  product_match_status?: string | null;
  checks: OrderCheck[];
}
