import { Link } from "react-router-dom";
import type { Product } from "../lib/catalog";
import { formatMoney } from "../lib/money";

/**
 * Catalog grid cell: product name (link to detail), description, and
 * price. Availability is text, never color-only; the browse endpoint
 * only returns active products, so an inactive flag renders defensively.
 */
export function ProductCard({ product }: { product: Product }) {
  const detailPath = `/catalog/${encodeURIComponent(product.id)}`;
  return (
    <article className="product-card" aria-labelledby={`product-name-${product.id}`}>
      <h2 id={`product-name-${product.id}`} className="product-name">
        <Link to={detailPath}>{product.name}</Link>
      </h2>
      {product.description ? <p className="product-description">{product.description}</p> : null}
      <p className="product-price">
        <span className="visually-hidden">Price: </span>
        {formatMoney(product.price, product.currency)}
      </p>
      {!product.active ? (
        <p className="badge badge-warning" role="status">
          Unavailable
        </p>
      ) : null}
      <p>
        <Link className="button button-secondary" to={detailPath} aria-label={`View ${product.name}`}>
          View details
        </Link>
      </p>
    </article>
  );
}
