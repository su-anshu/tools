# Mithila Foods Shopify Theme

A custom Shopify theme designed specifically for the Mithila Foods website, featuring authentic Indian food e-commerce design with a clean, modern interface and vibrant green color scheme.

## Theme Overview

This theme is a complete Shopify clone of the original Mithila Foods website (https://www.mithilafoods.com/), featuring:

- **Responsive Design**: Fully optimized for desktop, tablet, and mobile devices
- **Green Color Scheme**: Matching the original site's vibrant green branding (#4CAF50)
- **Indian Food Focus**: Designed specifically for traditional Indian grocery and food products
- **Modern E-commerce Features**: Complete shopping cart, product variants, search, and checkout functionality

## Features

### Core Functionality
- ✅ Complete Shopify theme structure
- ✅ Responsive header with navigation and search
- ✅ Hero banner sections with overlay content
- ✅ Product grid displays with "Best Deals" sections
- ✅ Featured product sections with variant selection
- ✅ Customer testimonials and reviews
- ✅ Footer with newsletter signup and social links
- ✅ Product pages with full e-commerce functionality
- ✅ Collection pages with filtering and sorting

### Design Elements
- **Typography**: Roboto and Roboto Slab font families
- **Color Palette**: Green primary (#4CAF50), with lighter accents (#66BB6A)
- **Layout**: Clean grid-based design with proper spacing
- **Images**: Optimized responsive image handling
- **Animations**: Scroll-triggered animations and hover effects

### E-commerce Features
- Product variant selection (dropdowns and buttons)
- Quantity selectors with +/- controls
- Add to cart and buy now buttons
- Dynamic checkout integration
- Product media galleries
- Customer reviews and ratings
- Search functionality
- Newsletter signup
- Social media integration

## File Structure

```
mithila-shopify-theme/
├── assets/
│   └── mithila-theme.css          # Main stylesheet (608 lines)
├── config/
│   ├── settings_data.json         # Theme settings configuration
│   └── settings_schema.json       # Theme customization options
├── layout/
│   └── theme.liquid              # Main layout template (279 lines)
├── sections/
│   ├── header.liquid             # Site header and navigation (695 lines)
│   ├── footer.liquid             # Site footer (531 lines)
│   ├── image-banner.liquid       # Hero banner section (409 lines)
│   ├── multicolumn.liquid        # Feature cards section (388 lines)
│   ├── featured-product.liquid   # Product showcase (777 lines)
│   ├── featured-collection.liquid # Product grid section (433 lines)
│   └── testimonials.liquid       # Customer reviews (435 lines)
├── snippets/
│   ├── card-product.liquid       # Product card component (257 lines)
│   ├── price.liquid              # Price display component (85 lines)
│   └── social-icons.liquid       # Social media icons (88 lines)
├── templates/
│   ├── index.liquid              # Homepage template
│   ├── product.liquid            # Product page template (579 lines)
│   └── collection.liquid         # Collection page template (174 lines)
└── locales/
    └── en.default.json           # English translations
```

## Installation Instructions

1. **Download Theme Files**: Download all theme files from this directory
2. **Create Theme Archive**: Zip all files maintaining the folder structure
3. **Upload to Shopify**:
   - Go to Online Store > Themes in your Shopify admin
   - Click "Add theme" > "Upload zip file"
   - Select your theme archive and upload
4. **Activate Theme**: Once uploaded, click "Publish" to make it live

## Customization

### Theme Settings
The theme includes comprehensive customization options:

- **Colors**: Modify color schemes, accent colors, and background colors
- **Typography**: Change fonts, font sizes, and text scaling
- **Layout**: Adjust page width, spacing, and grid layouts
- **Buttons**: Customize button styles, borders, and shadows
- **Cards**: Configure product card appearance and styling
- **Branding**: Upload logo, set social media links, and configure brand assets

### Section Settings
Each section can be customized through the Shopify theme editor:

- **Header**: Logo placement, navigation menus, search settings
- **Image Banner**: Background images, overlay content, button links
- **Featured Products**: Product selection, display options, layout
- **Featured Collections**: Collection selection, grid layout, filtering
- **Testimonials**: Customer reviews, ratings, display options
- **Footer**: Newsletter settings, social links, payment options

## Development Notes

### CSS Framework
- Custom CSS built from scratch to match original design
- CSS variables for consistent theming
- Responsive breakpoints: 750px (tablet), 990px (desktop)
- Grid-based layouts with flexbox fallbacks

### Liquid Templating
- Full Shopify Liquid syntax implementation
- Schema definitions for theme customization
- Dynamic content rendering
- SEO-optimized structured data

### Performance Optimizations
- Lazy loading for images
- Minified CSS and optimized assets
- Efficient Liquid loops and conditionals
- Progressive enhancement for JavaScript features

## Browser Support

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)
- Mobile browsers (iOS Safari, Chrome Mobile)

## License

This theme is created specifically for Mithila Foods and is based on their existing website design. All design elements, color schemes, and branding match their original site.

## Support

For theme customization, bug reports, or feature requests, please contact the development team.

---

**Version**: 1.0.0  
**Created**: August 2025  
**Shopify Theme**: Compatible with Shopify's latest theme requirements  
**Total Lines of Code**: 4,000+ lines across all theme files